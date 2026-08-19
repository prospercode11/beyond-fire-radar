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

function isPathInside(candidate, parent) {
  const relative = path.relative(path.resolve(parent), path.resolve(candidate));
  return relative !== "" && !relative.startsWith("..") && !path.isAbsolute(relative);
}

module.exports = {
  BACKEND_PORT,
  buildBackendEnvironment,
  desktopDataPaths,
  isPathInside,
  sqliteUrl,
};
