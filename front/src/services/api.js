// src/services/api.js
let baseUrl = "";
let token = "";

function setBackendConfig(cfg) {
  baseUrl = cfg.baseUrl;
  token = cfg.token;
}

async function http(path, options = {}) {
  const headers = {
    ...(options.headers || {}),
    ...(token ? { "X-Token": token } : {}),
    "Content-Type": "application/json",
  };

  const res = await fetch(`${baseUrl}${path}`, { ...options, headers });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} ${path} ${text}`);
  }
  return res.json().catch(() => ({}));
}

function health() {
  return fetch(`${baseUrl}/health`, { headers: token ? { "X-Token": token } : {} })
    .then((r) => r.ok);
}

function captureAndRecognize(projectId) {
  return http("/capture-and-recognize", {
    method: "POST",
    body: JSON.stringify({ projectId }),
  });
}

function confirmTarget(jobId, targetLabel) {
  return http("/confirm-target", {
    method: "POST",
    body: JSON.stringify({ jobId, targetLabel }),
  });
}

function getJob(jobId) {
  return http(`/jobs/${jobId}`, { method: "GET" });
}

// 静态文件：注意缓存（文档强调要加时间戳或 no-cache）:contentReference[oaicite:18]{index=18}
function fileUrl(p) {
  const t = Date.now();
  return `${baseUrl}${p}?t=${t}`;
}

module.exports = { setBackendConfig, health, captureAndRecognize, confirmTarget, getJob, fileUrl };
