"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");
const {
  BACKEND_PORT,
  buildBackendEnvironment,
  desktopDataPaths,
  isPathInside,
  sqliteUrl,
} = require("../runtime.cjs");

test("desktop data remains outside the replaceable installation directory", () => {
  const userData = path.resolve("C:/Users/Client/AppData/Roaming/Beyond Fire Radar");
  const resources = path.resolve("C:/Users/Client/AppData/Local/Programs/Beyond Fire Radar/resources");
  const resolved = desktopDataPaths(userData);
  assert.equal(resolved.databasePath, path.join(userData, "data", "beyond_fire_radar.db"));
  assert.equal(isPathInside(resolved.databasePath, resources), false);
  assert.equal(isPathInside(resolved.databasePath, userData), true);
});

test("backend environment starts all approved local pollers against the persistent database", () => {
  const resolved = desktopDataPaths("C:\\Users\\Client\\AppData\\Roaming\\Beyond Fire Radar");
  const environment = buildBackendEnvironment(resolved, "http://127.0.0.1:30055");
  assert.equal(environment.APP_ENV, "desktop");
  assert.equal(environment.API_PORT, String(BACKEND_PORT));
  assert.equal(environment.ENABLE_SARASOTA_POLLING_WORKER, "true");
  assert.equal(environment.ENABLE_MIAMI_DADE_POLLING_WORKER, "true");
  assert.equal(environment.ENABLE_BROWARD_POLLING_WORKER, "true");
  assert.equal(environment.DATABASE_URL, sqliteUrl(resolved.databasePath));
  assert.match(environment.DATABASE_URL, /^sqlite:\/\/\//);
});
