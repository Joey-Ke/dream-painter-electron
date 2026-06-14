// FILE: front/src/services/api.js
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

// 静态文件：注意缓存
function fileUrl(p) {
  const t = Date.now();
  return `${baseUrl}${p}?t=${t}`;
}

// 聊天接口（AI C）
function chat(messages, model = null, includeTts = false) {
  return http("/chat", {
    method: "POST",
    body: JSON.stringify({ messages, model, include_tts: includeTts }),
  });
}

// TTS接口
function textToSpeech(text, voice = null) {
  return http("/tts", {
    method: "POST",
    body: JSON.stringify({ text, voice }),
  });
}

// 生成视频接口
function generateVideo(taskId, stepIndices = null, fps = 12) {
  return http(`/tasks/${taskId}/generate-video`, {
    method: "POST",
    body: JSON.stringify({ task_id: taskId, step_indices: stepIndices, fps }),
  });
}

module.exports = { 
  setBackendConfig, 
  health, 
  captureAndRecognize, 
  confirmTarget, 
  getJob, 
  fileUrl,
  chat,
  textToSpeech,
  generateVideo,
};