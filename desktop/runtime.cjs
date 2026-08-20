"use strict";

const path = require("node:path");

const BACKEND_PORT = 28741;

function desktopDataPaths(userDataDirectory) {
  const dataDirectory = path.join(userDataDirectory, "data");
  return {
    userDataDirectory,
    dataDirectory,
    databasePath: path.join(dataDirectory, "beyond_fire_radar.db"),
    rawSnapshotDirectory: path.join(dataDirectory, "raw-snapshots"),
    backupDirectory: path.join(userDataDirectory, "backups"),
    logDirectory: path.join(userDataDirectory, "logs"),
  };
}

function sqliteUrl(databasePath) {
  return `sqlite:///${databasePath.replaceAll("\\", "/")}`;
}

function buildBackendEnvironment(paths, webOrigin) {
  return {
    APP_ENV: "desktop",
    APP_NAME: "Beyond Fire Radar",
    API_HOST: "127.0.0.1",
    API_PORT: String(BACKEND_PORT),
    DATABASE_URL: sqliteUrl(paths.databasePath),
    RAW_SNAPSHOT_DIR: paths.rawSnapshotDirectory,
    WEB_ORIGIN: webOrigin,
    ALLOWED_HOSTS: "127.0.0.1,localhost",
    ENABLE_API_DOCS: "false",
    ENABLE_LIVE_SARASOTA_DISPATCH_POLLING: "true",
    ENABLE_SARASOTA_POLLING_WORKER: "true",
    SARASOTA_LIVE_AUTHORIZATION_BASIS: "explicit_user_permission",
    ENABLE_LIVE_MIAMI_DADE_DISPATCH_POLLING: "true",
    ENABLE_MIAMI_DADE_POLLING_WORKER: "true",
    MIAMI_DADE_LIVE_AUTHORIZATION_BASIS: "explicit_user_permission",
    ENABLE_LIVE_BROWARD_DISPATCH_POLLING: "true",
    ENABLE_BROWARD_POLLING_WORKER: "true",
    BROWARD_LIVE_AUTHORIZATION_BASIS: "explicit_user_permission",
  };
}

const WEB_ENTRY_FILENAME = "server.js";
const BACKEND_DIRECTORY_NAME = "beyond-fire-radar-backend";

function backendExecutableName(platform) {
  return platform === "win32" ? `${BACKEND_DIRECTORY_NAME}.exe` : BACKEND_DIRECTORY_NAME;
}

function runtimeResourcePaths(resourcesPath, platform) {
  const webDirectory = path.join(resourcesPath, "web");
  const backendDirectory = path.join(resourcesPath, "backend", BACKEND_DIRECTORY_NAME);
  return {
    webDirectory,
    webServer: path.join(webDirectory, WEB_ENTRY_FILENAME),
    webStaticDirectory: path.join(webDirectory, ".next", "static"),
    webDependencyManifest: path.join(webDirectory, "node_modules", "next", "package.json"),
    backendDirectory,
    backendExecutable: path.join(backendDirectory, backendExecutableName(platform)),
  };
}

// Packaging skips a missing extraResources directory with a warning instead of an
// error, so the shell has to treat an incomplete installation as a first-class
// startup failure rather than discovering it one launch step at a time.
function missingRuntimeResources(resourcePaths, exists) {
  return [
    ["Dashboard server", resourcePaths.webServer],
    ["Dashboard browser assets", resourcePaths.webStaticDirectory],
    ["Dashboard dependencies", resourcePaths.webDependencyManifest],
    ["Background alert service", resourcePaths.backendExecutable],
  ]
    .filter(([, target]) => !exists(target))
    .map(([label, target]) => ({ label, path: target }));
}

function describeMissingResources(missing) {
  const details = missing.map((entry) => `${entry.label}: ${entry.path}`).join("\n");
  return [
    "This installation is incomplete, so Beyond Fire Radar cannot start.",
    "",
    "Missing from the installed application:",
    details,
    "",
    "Download the current installer and install it again. Your alert database, snapshots, and backups stay in your Windows user profile and are not affected.",
  ].join("\n");
}

function isPathInside(candidate, parent) {
  const relative = path.relative(path.resolve(parent), path.resolve(candidate));
  return relative !== "" && !relative.startsWith("..") && !path.isAbsolute(relative);
}

module.exports = {
  BACKEND_DIRECTORY_NAME,
  BACKEND_PORT,
  WEB_ENTRY_FILENAME,
  backendExecutableName,
  buildBackendEnvironment,
  describeMissingResources,
  desktopDataPaths,
  isPathInside,
  missingRuntimeResources,
  runtimeResourcePaths,
  sqliteUrl,
};
