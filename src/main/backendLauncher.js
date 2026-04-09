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

function parsePort(v) {
  if (!v) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/**
 * startBackend 返回：
 * { baseUrl, token, child, ready, error }
 * - ready: 后端是否健康可用
 * - error: 失败原因（用于 UI 显示）
 */
async function startBackend({ devPort, token }) {
  const isProd = app.isPackaged; // 关键：用“是否打包”区分环境

  // 允许用环境变量直接指定完整 URL（最灵活）
  const envUrl = process.env.BACKEND_URL;

  // 允许用端口指定（devPort 参数 > 环境变量 > 默认 8000）
  const port =
    parsePort(devPort) ||
    parsePort(process.env.BACKEND_PORT) ||
    8000;

  // ========== 1) 开发期：永远不 spawn ==========
  if (!isProd) {
    const baseUrl = envUrl || `http://127.0.0.1:${port}`;
    const ready = await waitHealth(baseUrl, token, 1500); // 开发期别等太久，避免启动卡住
    return {
      baseUrl,
      token,
      child: null,
      ready,
      error: ready ? null : `Backend not ready: ${baseUrl}`,
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
  });

  let realPort = null;

  child.stdout.on("data", (buf) => {
    const text = buf.toString();
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
