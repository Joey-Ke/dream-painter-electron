const { app, BrowserWindow } = require("electron");
const path = require("path");
const { initBackend, registerIpc, registerAppHooks } = require("./main/ipc");

let mainWindow;

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: MAIN_WINDOW_PRELOAD_WEBPACK_ENTRY,
      contextIsolation: true,
    },
  });

  await mainWindow.loadURL(MAIN_WINDOW_WEBPACK_ENTRY);
  mainWindow.webContents.openDevTools(); // 你现在就是这样打开 DevTools 的
}

app.whenReady().then(async () => {
  // 先启动后端并 health ok，再创建窗口进入 Ready（文档推荐）:contentReference[oaicite:15]{index=15}
  await initBackend();
  registerIpc();
  registerAppHooks();
  await createWindow();
});
