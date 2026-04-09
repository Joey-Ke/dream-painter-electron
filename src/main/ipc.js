// src/main/ipc.js
const { app, ipcMain, dialog } = require("electron");
const crypto = require("crypto");
const fs = require("fs");
const { startBackend, stopBackend } = require("./backendLauncher");

let backend = { baseUrl: null, token: null, child: null };

function genToken() {
  return crypto.randomBytes(16).toString("hex");
}

async function initBackend() {
  const token = genToken();
  const devPort = process.env.BACKEND_PORT; // 开发期：你可在命令行先 set BACKEND_PORT=8080
  backend = await startBackend({ devPort, token });
}

function registerIpc() {
  ipcMain.handle("backend:getConfig", async () => {
    return {
      baseUrl: backend.baseUrl,
      token: backend.token,
      ready: backend.ready,
      error: backend.error,
    };

  });

  ipcMain.handle("electron:showSaveDialog", async (event, options) => {
    return dialog.showSaveDialog(BrowserWindow.fromWebContents(event.sender), options);
  });

  ipcMain.handle("electron:writeFile", async (event, filePath, data) => {
    return new Promise((resolve, reject) => {
      fs.writeFile(filePath, data, (err) => {
        if (err) reject(err);
        else resolve();
      });
    });
  });
}

function registerAppHooks() {
  app.on("before-quit", () => {
    stopBackend(backend.child); // 文档要求退出时 kill 避免残留 :contentReference[oaicite:14]{index=14}
  });
}

module.exports = { initBackend, registerIpc, registerAppHooks };
