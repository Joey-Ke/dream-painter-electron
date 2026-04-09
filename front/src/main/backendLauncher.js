// src/main/backendLauncher.js
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const { app } = require("electron");

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function tryFetch(url, headers = {}) {
  const res = await fetch(url, { headers });
  return res;
}

async function waitHealth(baseUrl, token, timeoutMs = 5000) {
  const start = Date.now();
  const headers = token ? { "X-Token": token } : {};

  while (Date.now() - start < timeoutMs) {
    try {
      const res = await tryFetch(`${baseUrl}/health`, headers);
      if (res.ok) return true;
    } catch (_) {}

    try {
      const res = await tryFetch(`${baseUrl}/`, headers);
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
 */
async function startBackend({ devPort, token }) {
  const isProd = app.isPackaged;
  const envUrl = process.env.BACKEND_URL;

  const port =
    parsePort(devPort) ||
    parsePort(process.env.BACKEND_PORT) ||
    8000;

  // ========= 开发环境：不 spawn，直接连本地后端 =========
  if (!isProd) {
    const baseUrl = envUrl || `http://127.0.0.1:${port}`;
    const ready = await waitHealth(baseUrl, token, 5000);

    return {
      baseUrl,
      token,
      child: null,
      ready,
      error: ready ? null : `Backend not ready. Checked ${baseUrl}/health`,
    };
  }

  // ========= 生产环境：尝试启动打包后的 exe =========
  const backendExe = path.join(process.resourcesPath, "backend", "backend.exe");

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
    console.log("[backend stdout]", text);

    const m = text.match(/PORT=(\d+)/);
    if (m) realPort = Number(m[1]);
  });

  child.stderr.on("data", (buf) => {
    console.error("[backend stderr]", buf.toString());
  });

  const start = Date.now();
  while (!realPort && Date.now() - start < 5000) {
    await sleep(50);
  }

  const finalPort = realPort || port || 8000;
  const baseUrl = envUrl || `http://127.0.0.1:${finalPort}`;
  const ready = await waitHealth(baseUrl, token, 15000);

  if (!ready) {
    try { child.kill(); } catch (_) {}
    return {
      baseUrl,
      token,
      child: null,
      ready: false,
      error: realPort
        ? "Backend health check failed after spawn."
        : "Backend health check failed. No PORT=xxxx detected; fallback port also failed.",
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
