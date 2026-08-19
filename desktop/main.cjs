"use strict";

const {
  app,
  BrowserWindow,
  dialog,
  ipcMain,
  Menu,
  nativeImage,
  session,
  Tray,
} = require("electron");
const { autoUpdater } = require("electron-updater");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");
const {
  BACKEND_PORT,
  buildBackendEnvironment,
  desktopDataPaths,
  isPathInside,
} = require("./runtime.cjs");

const START_HIDDEN = process.argv.includes("--background");
const UPDATE_SUPPORTED = process.platform === "win32" && app.isPackaged;
const instanceLock = app.requestSingleInstanceLock();

let mainWindow = null;
let tray = null;
let backendProcess = null;
let webProcess = null;
let backendRestartTimer = null;
let runtimeUrl = null;
let isQuitting = false;
let updateStatus = {
  state: UPDATE_SUPPORTED ? "idle" : "unsupported",
  message: UPDATE_SUPPORTED
    ? "Ready to check GitHub for updates."
    : "Updates are available in the installed Windows app.",
  currentVersion: app.getVersion(),
};

if (!instanceLock) {
  app.quit();
}

function paths() {
  return desktopDataPaths(app.getPath("userData"));
}

function ensureDataDirectories() {
  const resolved = paths();
  for (const directory of [
    resolved.dataDirectory,
    resolved.rawSnapshotDirectory,
    resolved.backupDirectory,
    resolved.logDirectory,
  ]) {
    fs.mkdirSync(directory, { recursive: true });
  }
  return resolved;
}

function writeLog(message) {
  try {
    const resolved = ensureDataDirectories();
    fs.appendFileSync(
      path.join(resolved.logDirectory, "desktop.log"),
      `${new Date().toISOString()} ${message}\n`,
      "utf8",
    );
  } catch {
    // Logging must never take down the background polling process.
  }
}

function setUpdateStatus(next) {
  updateStatus = { ...updateStatus, ...next, currentVersion: app.getVersion() };
  for (const window of BrowserWindow.getAllWindows()) {
    window.webContents.send("updater:status", updateStatus);
  }
  return updateStatus;
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : null;
      server.close(() => (port ? resolve(port) : reject(new Error("No free local port"))));
    });
  });
}

async function waitForUrl(url, timeoutMs = 90000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (response.ok) return;
      lastError = new Error(`${url} returned ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(
    `Timed out waiting for ${url}: ${lastError instanceof Error ? lastError.message : "unavailable"}`,
  );
}

function backendExecutable() {
  const filename = process.platform === "win32" ? "beyond-fire-radar-backend.exe" : "beyond-fire-radar-backend";
  return path.join(process.resourcesPath, "backend", "beyond-fire-radar-backend", filename);
}

function webDirectory() {
  return path.join(process.resourcesPath, "web");
}

function attachProcessLogging(child, name) {
  child.stdout?.on("data", (chunk) => writeLog(`${name}: ${String(chunk).trimEnd()}`));
  child.stderr?.on("data", (chunk) => writeLog(`${name}: ${String(chunk).trimEnd()}`));
  child.on("error", (error) => writeLog(`${name} process error: ${error.message}`));
}

function launchBackend(environment) {
  const executable = backendExecutable();
  if (!fs.existsSync(executable)) throw new Error(`Backend executable is missing: ${executable}`);
  backendProcess = spawn(executable, ["serve"], {
    cwd: paths().dataDirectory,
    env: { ...process.env, ...environment },
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  attachProcessLogging(backendProcess, "backend");
  backendProcess.on("exit", (code, signal) => {
    backendProcess = null;
    writeLog(`backend exited code=${code} signal=${signal}`);
    if (!isQuitting) {
      clearTimeout(backendRestartTimer);
      backendRestartTimer = setTimeout(() => {
        try {
          launchBackend(environment);
        } catch (error) {
          writeLog(`backend restart failed: ${error.message}`);
        }
      }, 5000);
    }
  });
}

function launchWeb(webPort) {
  const directory = webDirectory();
  const server = path.join(directory, "server.js");
  if (!fs.existsSync(server)) throw new Error(`Web server is missing: ${server}`);
  webProcess = spawn(process.execPath, [server], {
    cwd: directory,
    env: {
      ...process.env,
      ELECTRON_RUN_AS_NODE: "1",
      HOSTNAME: "127.0.0.1",
      PORT: String(webPort),
      NODE_ENV: "production",
    },
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  attachProcessLogging(webProcess, "web");
  webProcess.on("exit", (code, signal) => {
    webProcess = null;
    writeLog(`web exited code=${code} signal=${signal}`);
  });
}

async function startRuntime() {
  const resolved = ensureDataDirectories();
  if (isPathInside(resolved.databasePath, process.resourcesPath)) {
    throw new Error("Refusing to store the alert database inside the replaceable app directory.");
  }
  const webPort = await findFreePort();
  runtimeUrl = `http://127.0.0.1:${webPort}`;
  const backendEnvironment = buildBackendEnvironment(resolved, runtimeUrl);
  launchBackend(backendEnvironment);
  await waitForUrl(`http://127.0.0.1:${BACKEND_PORT}/readyz`);
  launchWeb(webPort);
  await waitForUrl(runtimeUrl);
  writeLog(`runtime ready at ${runtimeUrl}; data at ${resolved.dataDirectory}`);
}

function createWindow() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.show();
    mainWindow.focus();
    return mainWindow;
  }
  const iconPath = path.join(__dirname, "assets", "icon.png");
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1040,
    minHeight: 700,
    show: false,
    backgroundColor: "#f4f1ea",
    icon: iconPath,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow.removeMenu();
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!runtimeUrl || !url.startsWith(runtimeUrl)) event.preventDefault();
  });
  mainWindow.on("close", (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
  mainWindow.loadURL(runtimeUrl);
  mainWindow.once("ready-to-show", () => mainWindow.show());
  return mainWindow;
}

function createTray() {
  const iconPath = path.join(__dirname, "assets", "icon.png");
  const icon = nativeImage.createFromPath(iconPath).resize({ width: 16, height: 16 });
  tray = new Tray(icon);
  tray.setToolTip("Beyond Fire Radar — background alert checking is running");
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: "Open Beyond Fire Radar", click: () => createWindow() },
      { label: "Check for updates", click: () => void checkForUpdates() },
      { type: "separator" },
      {
        label: "Quit and stop alert checking",
        click: () => {
          isQuitting = true;
          app.quit();
        },
      },
    ]),
  );
  tray.on("double-click", () => createWindow());
}

function configureUpdater() {
  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = false;
  autoUpdater.on("checking-for-update", () =>
    setUpdateStatus({ state: "checking", message: "Checking GitHub for a newer version…" }),
  );
  autoUpdater.on("update-available", (info) =>
    setUpdateStatus({
      state: "available",
      availableVersion: info.version,
      message: `Version ${info.version} is available.`,
    }),
  );
  autoUpdater.on("update-not-available", () =>
    setUpdateStatus({ state: "current", message: "You have the latest version." }),
  );
  autoUpdater.on("download-progress", (progress) =>
    setUpdateStatus({
      state: "downloading",
      percent: Math.round(progress.percent),
      message: `Downloading update… ${Math.round(progress.percent)}%`,
    }),
  );
  autoUpdater.on("update-downloaded", (info) =>
    setUpdateStatus({
      state: "downloaded",
      availableVersion: info.version,
      percent: 100,
      message: "Update ready. Restart to install it.",
    }),
  );
  autoUpdater.on("error", (error) =>
    setUpdateStatus({ state: "error", message: `Update check failed: ${error.message}` }),
  );
}

async function checkForUpdates() {
  if (!UPDATE_SUPPORTED) return setUpdateStatus({ state: "unsupported" });
  await autoUpdater.checkForUpdates();
  return updateStatus;
}

function runBackendCommand(argumentsList) {
  return new Promise((resolve, reject) => {
    const child = spawn(backendExecutable(), argumentsList, {
      cwd: paths().dataDirectory,
      env: process.env,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let errorText = "";
    child.stderr?.on("data", (chunk) => {
      errorText += String(chunk);
    });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(errorText.trim() || `Backend command exited with ${code}`));
    });
  });
}

async function createPreUpdateBackup() {
  const resolved = ensureDataDirectories();
  if (!fs.existsSync(resolved.databasePath)) return null;
  const version = updateStatus.availableVersion ?? "unknown";
  const timestamp = new Date().toISOString().replaceAll(":", "-").replaceAll(".", "-");
  const output = path.join(resolved.backupDirectory, `pre-update-${version}-${timestamp}.sqlite`);
  await runBackendCommand([
    "backup",
    "--database",
    resolved.databasePath,
    "--output",
    output,
  ]);
  const backups = fs
    .readdirSync(resolved.backupDirectory)
    .filter((name) => name.startsWith("pre-update-") && name.endsWith(".sqlite"))
    .sort()
    .reverse();
  for (const oldName of backups.slice(1)) {
    fs.unlinkSync(path.join(resolved.backupDirectory, oldName));
  }
  writeLog(`created pre-update database backup ${output}`);
  return output;
}

async function stopServices() {
  clearTimeout(backendRestartTimer);
  backendRestartTimer = null;
  for (const child of [webProcess, backendProcess]) {
    if (child && !child.killed) child.kill();
  }
  webProcess = null;
  backendProcess = null;
}

ipcMain.handle("desktop:get-runtime-info", () => ({
  version: app.getVersion(),
  dataDirectory: paths().dataDirectory,
  startsAtLogin:
    process.platform === "win32" && app.isPackaged
      ? app.getLoginItemSettings().openAtLogin
      : false,
}));
ipcMain.handle("updater:get-status", () => updateStatus);
ipcMain.handle("updater:check", () => checkForUpdates());
ipcMain.handle("updater:download", async () => {
  if (updateStatus.state !== "available") throw new Error("No update is ready to download.");
  await autoUpdater.downloadUpdate();
  return updateStatus;
});
ipcMain.handle("updater:install", async () => {
  if (updateStatus.state !== "downloaded") throw new Error("Download the update first.");
  try {
    setUpdateStatus({ state: "installing", message: "Backing up alert data before restart…" });
    await createPreUpdateBackup();
    isQuitting = true;
    await stopServices();
    autoUpdater.quitAndInstall(false, true);
  } catch (error) {
    setUpdateStatus({
      state: "error",
      message: `Update stopped before installation: ${error.message}`,
    });
    throw error;
  }
  return updateStatus;
});

app.on("second-instance", () => {
  if (runtimeUrl) createWindow();
});

app.on("before-quit", () => {
  isQuitting = true;
  void stopServices();
});

app.on("window-all-closed", () => {
  // Keep the tray and background pollers alive on Windows.
});

app.whenReady().then(async () => {
  try {
    session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) =>
      callback(false),
    );
    if (process.platform === "win32" && app.isPackaged) {
      app.setLoginItemSettings({ openAtLogin: true, args: ["--background"] });
    }
    configureUpdater();
    await startRuntime();
    createTray();
    if (!START_HIDDEN) createWindow();
  } catch (error) {
    writeLog(`startup failed: ${error.stack ?? error.message}`);
    dialog.showErrorBox(
      "Beyond Fire Radar could not start",
      `${error.message}\n\nSee ${path.join(paths().logDirectory, "desktop.log")} for details.`,
    );
    isQuitting = true;
    app.quit();
  }
});
