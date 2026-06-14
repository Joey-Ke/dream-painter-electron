// src/main/backendLauncher.js
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const { app } = require("electron");

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function waitHealth(baseUrl, token, timeoutMs = 3000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(`${baseUrl}/health`, {
        headers: token ? { "X-Token": token } : {},
      });
      if (res.ok) return true;
    } catch (_) {}
    await sleep(300);
  }
  return false;
}

function pipeBackendLogs(child, label) {
  child.stdout.on("data", (buf) => {
    console.log(`[${label} stdout]`, buf.toString());
  });

  child.stderr.on("data", (buf) => {
    console.error(`[${label} stderr]`, buf.toString());
  });
}

function parsePort(v) {
  if (!v) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

async function startDevBackend({ port, token, baseUrl }) {
  const backendDir = path.join(process.cwd(), "backend", "backend");
  const pythonCandidates = [
    path.join(backendDir, ".venv311", "Scripts", "python.exe"),
    path.join(backendDir, ".venv", "Scripts", "python.exe"),
    "python",
  ];
  const python = pythonCandidates.find((candidate) => {
    return candidate === "python" || fs.existsSync(candidate);
  });

  if (!fs.existsSync(backendDir)) {
    return {
      child: null,
      ready: false,
      error: `Dev backend directory not found: ${backendDir}`,
    };
  }

  const child = spawn(
    python,
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(port)],
    {
      cwd: backendDir,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
      env: {
        ...process.env,
        BACKEND_PORT: String(port),
        BACKEND_TOKEN: token,
        PYTHONDONTWRITEBYTECODE: "1",
        PYTHONIOENCODING: "utf-8",
      },
    },
  );

  pipeBackendLogs(child, "dev backend");

  const ready = await waitHealth(baseUrl, token, 15000);
  if (!ready) {
    try { child.kill(); } catch (_) {}
    return {
      child: null,
      ready: false,
      error: `Dev backend failed to start: ${baseUrl}`,
    };
  }

  return { child, ready: true, error: null };
}

/**
 * startBackend 返回：
 * { baseUrl, token, child, ready, error }
 * - ready: 后端是否健康可用
 * - error: 失败原因（用于 UI 显示）
 */
async function startBackend({ devPort, token }) {
  const isProd = app.isPackaged; // 关键：用“是否打包”区分环境

  // 如果外部环境已指定后端 token，则优先使用它
  const envToken = process.env.BACKEND_TOKEN;
  token = token || envToken;

  // 允许用环境变量直接指定完整 URL（最灵活）
  const envUrl = process.env.BACKEND_URL;

  // 允许用端口指定（devPort 参数 > 环境变量 > 默认 8000）
  const port =
    parsePort(devPort) ||
    parsePort(process.env.BACKEND_PORT) ||
    8000;

  // ========== 1) 开发期：优先复用已有后端，未启动时自动拉起 ==========
  if (!isProd) {
    const baseUrl = envUrl || `http://127.0.0.1:${port}`;
    let ready = await waitHealth(baseUrl, token, 1500); // 开发期先探测已有后端
    let child = null;
    let error = ready ? null : `Backend not ready: ${baseUrl}`;

    if (!ready && !envUrl) {
      const started = await startDevBackend({ port, token, baseUrl });
      ready = started.ready;
      child = started.child;
      error = started.error;
    }

    return {
      baseUrl,
      token,
      child,
      ready,
      error,
    };
  }

  // ========== 2) 生产期：尝试 spawn ==========
  const backendExe = path.join(process.resourcesPath, "backend", "backend.exe");

  // 生产期也要防御：exe 不存在就不要崩
  if (!fs.existsSync(backendExe)) {
    const baseUrl = envUrl || `http://127.0.0.1:${port}`;
    return {
      baseUrl,
      token,
      child: null,
      ready: false,
      error: `backend.exe not found: ${backendExe}`,
    };
  }

  const child = spawn(backendExe, [], {
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
    env: { ...process.env, BACKEND_TOKEN: token, PYTHONIOENCODING: "utf-8" },
  });

  let realPort = null;

  child.stdout.on("data", (buf) => {
    const text = buf.toString();
    console.log("[backend stdout]", text);
    const m = text.match(/PORT=(\d+)/);
    if (m) realPort = Number(m[1]);
  });

  child.stderr.on("data", (buf) => {
    console.error("[backend stderr]", buf.toString());
  });

  // 等待拿到端口
  const start = Date.now();
  while (!realPort && Date.now() - start < 5000) {
    await sleep(50);
  }

  if (!realPort) {
    try { child.kill(); } catch (_) {}
    const baseUrl = envUrl || `http://127.0.0.1:${port}`;
    return {
      baseUrl,
      token,
      child: null,
      ready: false,
      error: "Failed to get backend port from stdout (need PORT=xxxx).",
    };
  }

  const baseUrl = `http://127.0.0.1:${realPort}`;
  const ready = await waitHealth(baseUrl, token, 15000);

  if (!ready) {
    try { child.kill(); } catch (_) {}
    return {
      baseUrl,
      token,
      child: null,
      ready: false,
      error: "Backend health check failed after spawn.",
    };
  }

  return { baseUrl, token, child, ready, error: null };
}

function stopBackend(child) {
  if (!child) return;
  try {
    child.kill();
  } catch (_) {}
}

module.exports = { startBackend, stopBackend };
