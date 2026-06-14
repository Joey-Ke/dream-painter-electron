let baseUrl = "";
let token = "";

function setBackendConfig(cfg = {}) {
  baseUrl = (cfg.baseUrl || "").replace(/\/$/, "");
  token = cfg.token || "";
}

function authHeaders(extra = {}) {
  return {
    ...extra,
    ...(token ? { "X-Token": token } : {}),
  };
}

async function readError(res, path) {
  const text = await res.text().catch(() => "");
  if (!text) return `HTTP ${res.status} ${path}`;

  try {
    const payload = JSON.parse(text);
    const detail = payload.detail || payload.error || text;
    return typeof detail === "string"
      ? `HTTP ${res.status} ${path}: ${detail}`
      : `HTTP ${res.status} ${path}: ${JSON.stringify(detail)}`;
  } catch (_) {
    return `HTTP ${res.status} ${path}: ${text}`;
  }
}

async function health() {
  if (!baseUrl) return false;
  const res = await fetch(`${baseUrl}/health`, {
    headers: authHeaders(),
    cache: "no-store",
  });
  return res.ok;
}

async function createTask({ imageBlob, prompt = "" }) {
  if (!baseUrl) throw new Error("Backend baseUrl is empty.");
  if (!imageBlob) throw new Error("imageBlob is required.");

  const form = new FormData();
  form.append("image", imageBlob, "capture.jpg");
  form.append("prompt", prompt || "");

  const path = "/tasks";
  const res = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers: authHeaders(),
    body: form,
  });

  if (!res.ok) throw new Error(await readError(res, path));
  return res.json();
}

async function getTask(taskId) {
  if (!baseUrl) throw new Error("Backend baseUrl is empty.");
  if (!taskId) throw new Error("taskId is required.");

  const path = `/tasks/${encodeURIComponent(taskId)}`;
  const res = await fetch(`${baseUrl}${path}`, {
    headers: authHeaders(),
    cache: "no-store",
  });

  if (!res.ok) throw new Error(await readError(res, path));
  return res.json();
}

function appendQuery(url, params = {}) {
  const query = Object.entries(params)
    .filter(([, value]) => value != null && value !== "")
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`)
    .join("&");
  if (!query) return url;
  const joiner = url.includes("?") ? "&" : "?";
  return `${url}${joiner}${query}`;
}

function appendTimestamp(url) {
  return appendQuery(url, { t: Date.now() });
}

function appendMediaAuth(url) {
  return appendQuery(url, token ? { token } : {});
}

function assetUrl(path) {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return appendTimestamp(path);

  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return appendTimestamp(appendMediaAuth(`${baseUrl}${normalizedPath}`));
}

function frameUrl(taskId, k) {
  const safeTaskId = encodeURIComponent(taskId);
  const safeIndex = Math.max(0, Number(k) || 0);
  return appendTimestamp(appendMediaAuth(`${baseUrl}/tasks/${safeTaskId}/steps/${safeIndex}/frame`));
}

module.exports = {
  setBackendConfig,
  health,
  createTask,
  getTask,
  assetUrl,
  frameUrl,
};
