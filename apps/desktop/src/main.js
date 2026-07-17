const { app, BrowserWindow, Menu, shell } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");
const path = require("path");

const APP_ROOT = process.env.AEN_ROOT || "D:\\AgenticEngineeringNetwork";
const WEB_URL = process.env.AEN_WEB_URL || "http://localhost:3000";
const DESKTOP_WEB_URL = process.env.AEN_DESKTOP_WEB_URL || "http://127.0.0.1:3001";
const HEALTH_URL = process.env.AEN_HEALTH_URL || "http://localhost:8000/api/health";

let mainWindow;
let serviceProcess;
let webProcess;
let apiProcess;
let activeWebUrl = WEB_URL;

function appendLauncherLog(message) {
  try {
    const logPath = path.join(APP_ROOT, "logs", "desktop-launcher.log");
    fs.mkdirSync(path.dirname(logPath), { recursive: true });
    fs.appendFileSync(logPath, `${new Date().toISOString()} ${message}\n`, "utf8");
  } catch {
    // Logging must never block the desktop shell from trying to start.
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1180,
    minHeight: 760,
    backgroundColor: "#0f172a",
    title: "Agentic Engineering Network",
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (!url.startsWith(WEB_URL) && !url.startsWith(DESKTOP_WEB_URL)) {
      shell.openExternal(url);
      return { action: "deny" };
    }
    const child = new BrowserWindow({
      width: 960,
      height: 760,
      minWidth: 520,
      minHeight: 420,
      backgroundColor: "#0f1216",
      title: "Agentic Engineering Network",
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true
      }
    });
    child.loadURL(url);
    return { action: "deny" };
  });

  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function setAppMenu() {
  const template = [
    {
      label: "Agentic Engineering Network",
      submenu: [
        { label: "Reload", accelerator: "Ctrl+R", click: () => mainWindow?.reload() },
        { label: "Open API Docs", click: () => shell.openExternal("http://localhost:8000/docs") },
        { type: "separator" },
        { label: "Quit", accelerator: "Alt+F4", role: "quit" }
      ]
    },
    {
      label: "View",
      submenu: [
        { role: "toggleDevTools" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" }
      ]
    }
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

function requestOk(url, timeoutMs = 2500) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      res.resume();
      resolve(res.statusCode >= 200 && res.statusCode < 500);
    });
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
    req.on("error", () => resolve(false));
  });
}

async function waitForUrl(url, attempts = 90, delayMs = 2000) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (await requestOk(url)) {
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  return false;
}

function startServices(services = ["postgres", "api", "web"]) {
  if (serviceProcess) {
    return;
  }
  const scriptPath = path.join(APP_ROOT, "start.ps1");
  appendLauncherLog(`starting services via ${scriptPath}: ${services.join(",")}`);
  const serviceArgs = ["-Services", ...services];
  serviceProcess = spawn(
    "powershell.exe",
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", scriptPath, ...serviceArgs],
    {
      cwd: APP_ROOT,
      windowsHide: true,
      detached: false,
      stdio: "ignore"
    }
  );
  serviceProcess.on("error", () => {
    appendLauncherLog("failed to spawn start.ps1");
    serviceProcess = null;
  });
  serviceProcess.on("exit", (code) => {
    appendLauncherLog(`start.ps1 exited with code ${code}`);
    serviceProcess = null;
  });
}

function startDesktopWeb() {
  if (webProcess) {
    return true;
  }
  const command = process.platform === "win32" ? "node.exe" : "node";
  const webRoot = path.join(APP_ROOT, "apps", "web");
  const standaloneServer = path.join(webRoot, ".next", "standalone", "apps", "web", "server.js");
  const standaloneStatic = path.join(webRoot, ".next", "standalone", "apps", "web", ".next", "static");
  if (!fs.existsSync(standaloneServer) || !fs.existsSync(standaloneStatic)) {
    appendLauncherLog(
      `desktop web build is incomplete (server=${fs.existsSync(standaloneServer)}, static=${fs.existsSync(standaloneStatic)})`
    );
    return false;
  }
  appendLauncherLog(`starting desktop web fallback at ${DESKTOP_WEB_URL}`);
  webProcess = spawn(command, [standaloneServer], {
    cwd: webRoot,
    windowsHide: true,
    detached: false,
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      HOSTNAME: "127.0.0.1",
      PORT: "3001",
      NEXT_TELEMETRY_DISABLED: "1"
    }
  });
  webProcess.on("error", () => {
    appendLauncherLog("failed to spawn desktop web fallback");
    webProcess = null;
  });
  webProcess.stdout?.on("data", (data) => appendLauncherLog(`web stdout: ${data.toString().trim()}`));
  webProcess.stderr?.on("data", (data) => appendLauncherLog(`web stderr: ${data.toString().trim()}`));
  webProcess.on("exit", (code) => {
    appendLauncherLog(`desktop web fallback exited with code ${code}`);
    webProcess = null;
  });
  return true;
}

function apiPythonPath() {
  return process.env.AEN_API_PYTHON || "python.exe";
}

function apiPythonPathEnv() {
  return [
    path.join(APP_ROOT, "packages", "agents"),
    path.join(APP_ROOT, "packages", "orchestration"),
    path.join(APP_ROOT, "packages", "sandbox"),
    path.join(APP_ROOT, "packages", "git"),
    path.join(APP_ROOT, "packages", "logs"),
    path.join(APP_ROOT, "packages", "shared"),
    path.join(APP_ROOT, "packages", "database"),
    path.join(APP_ROOT, "packages", "security"),
    path.join(APP_ROOT, "apps", "api")
  ].join(";");
}

function startLocalApi() {
  if (apiProcess) {
    return;
  }
  const apiRoot = path.join(APP_ROOT, "apps", "api");
  appendLauncherLog(`starting local API fallback with ${apiPythonPath()}`);
  apiProcess = spawn(apiPythonPath(), ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"], {
    cwd: apiRoot,
    windowsHide: true,
    detached: false,
    stdio: ["ignore", "pipe", "pipe"],
    env: {
      ...process.env,
      AEN_ROOT: APP_ROOT,
      AEN_HOST_ROOT: APP_ROOT,
      AEN_HOST_WORKSPACE_DRIVE: "D:",
      AEN_WORKSPACE_DRIVE_MOUNT: "D:",
      PYTHONPATH: apiPythonPathEnv()
    }
  });
  apiProcess.on("error", () => {
    appendLauncherLog("failed to spawn local API fallback");
    apiProcess = null;
  });
  apiProcess.stdout?.on("data", (data) => appendLauncherLog(`api stdout: ${data.toString().trim()}`));
  apiProcess.stderr?.on("data", (data) => appendLauncherLog(`api stderr: ${data.toString().trim()}`));
  apiProcess.on("exit", (code) => {
    appendLauncherLog(`local API fallback exited with code ${code}`);
    apiProcess = null;
  });
}

async function ensureApiReady() {
  if (await requestOk(HEALTH_URL, 1200)) {
    return true;
  }
  startLocalApi();
  if (await waitForUrl(HEALTH_URL, 20, 1000)) {
    return true;
  }
  appendLauncherLog("local API fallback did not become ready; trying Docker postgres/api services");
  startServices(["postgres", "api"]);
  return waitForUrl(HEALTH_URL, 45, 2000);
}

function stopChildProcess(childProcess) {
  if (!childProcess || childProcess.killed) {
    return;
  }
  try {
    childProcess.kill();
  } catch {
    // Best effort cleanup. Services started by start.ps1 remain user-controlled.
  }
}

function loadingHtml(message) {
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Agentic Engineering Network</title>
  <style>
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #0f172a;
      color: #e5e7eb;
      font-family: Segoe UI, Arial, sans-serif;
    }
    main {
      width: min(720px, calc(100vw - 64px));
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 28px;
      background: #111827;
    }
    h1 {
      margin: 0 0 12px;
      font-size: 24px;
      font-weight: 650;
    }
    p {
      margin: 8px 0;
      color: #cbd5e1;
      line-height: 1.5;
    }
    code {
      color: #93c5fd;
    }
  </style>
</head>
<body>
  <main>
    <h1>Agentic Engineering Network</h1>
    <p>${message}</p>
    <p>Root: <code>${APP_ROOT}</code></p>
  </main>
</body>
</html>`;
}

async function boot() {
  appendLauncherLog("boot requested");
  createWindow();
  setAppMenu();
  await mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(loadingHtml("Starting local services..."))}`);

  const apiReady = ensureApiReady();
  const desktopWebAlreadyReady = await requestOk(DESKTOP_WEB_URL, 1200);
  if (desktopWebAlreadyReady) {
    appendLauncherLog(`reusing existing desktop web ${DESKTOP_WEB_URL}`);
  }
  const desktopWebStarted = desktopWebAlreadyReady || startDesktopWeb();
  if (desktopWebStarted && await waitForUrl(DESKTOP_WEB_URL, 45, 1000)) {
    activeWebUrl = DESKTOP_WEB_URL;
    appendLauncherLog(`loading desktop web fallback ${activeWebUrl}`);
    await mainWindow.loadURL(activeWebUrl);
    await apiReady;
    return;
  }

  if (await requestOk(WEB_URL, 1200)) {
    activeWebUrl = WEB_URL;
    appendLauncherLog(`loading existing web UI ${activeWebUrl}`);
    await mainWindow.loadURL(activeWebUrl);
    await apiReady;
    return;
  }

  await apiReady;

  if (await waitForUrl(WEB_URL, 30, 2000)) {
    activeWebUrl = WEB_URL;
    appendLauncherLog(`loading docker web UI ${activeWebUrl}`);
    await mainWindow.loadURL(activeWebUrl);
    return;
  }

  appendLauncherLog("failed to start any local web UI");
  await mainWindow.loadURL(
    `data:text/html;charset=utf-8,${encodeURIComponent(
      loadingHtml("Could not start the local web interface. Run npm --workspace apps/web run start:desktop, or start Docker services with start.ps1. See logs/desktop-launcher.log for details.")
    )}`
  );
}

app.whenReady().then(boot);

app.on("window-all-closed", () => {
  stopChildProcess(webProcess);
  stopChildProcess(apiProcess);
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  stopChildProcess(webProcess);
  stopChildProcess(apiProcess);
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    boot();
  }
});
