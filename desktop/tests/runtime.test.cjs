"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");
const {
  BACKEND_PORT,
  buildBackendEnvironment,
  describeMissingResources,
  desktopDataPaths,
  isPathInside,
  missingRuntimeResources,
  runtimeResourcePaths,
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

test("packaged Windows resource layout matches what the shell launches", () => {
  const resources = "C:\\Users\\Client\\AppData\\Local\\Programs\\Beyond Fire Radar\\resources";
  const resolved = runtimeResourcePaths(resources, "win32");
  assert.equal(resolved.webServer, path.join(resources, "web", "server.js"));
  assert.equal(resolved.webStaticDirectory, path.join(resources, "web", ".next", "static"));
  assert.equal(
    resolved.backendExecutable,
    path.join(
      resources,
      "backend",
      "beyond-fire-radar-backend",
      "beyond-fire-radar-backend.exe",
    ),
  );
  assert.equal(
    runtimeResourcePaths(resources, "darwin").backendExecutable,
    path.join(resources, "backend", "beyond-fire-radar-backend", "beyond-fire-radar-backend"),
  );
});

test("a packaged tree without the bundled dashboard is reported as incomplete", () => {
  const resolved = runtimeResourcePaths("/opt/app/resources", "win32");
  const present = new Set([resolved.backendExecutable]);
  const missing = missingRuntimeResources(resolved, (target) => present.has(target));
  assert.deepEqual(
    missing.map((entry) => entry.path),
    [resolved.webServer, resolved.webStaticDirectory, resolved.webDependencyDirectory],
  );
  const message = describeMissingResources(missing);
  assert.match(message, /installation is incomplete/);
  assert.match(message, /server\.js/);
  assert.match(message, /install it again/);
});

test("a fully packaged tree reports nothing missing", () => {
  const resolved = runtimeResourcePaths("/opt/app/resources", "win32");
  assert.deepEqual(missingRuntimeResources(resolved, () => true), []);
});
