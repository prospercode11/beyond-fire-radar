"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { build } = require("../package.json");

// app-builder-lib's copy filter rejects a matcher's own root node_modules before
// any pattern is applied (see util/filter.js: `if (relative === "node_modules")
// return false`). A single {from: ".build/web"} mapping therefore packages the
// dashboard without its dependencies, and it does so silently.
test("the dashboard's dependencies are mapped as their own resource entry", () => {
  const entries = build.extraResources;
  const web = entries.find((entry) => entry.from === ".build/web");
  const dependencies = entries.find((entry) => entry.from === ".build/web/node_modules");

  assert.ok(web, "the prepared web runtime must be packaged");
  assert.equal(web.to, "web");
  assert.ok(
    dependencies,
    "node_modules must be its own extraResources entry or the packager drops it",
  );
  assert.equal(dependencies.to, "web/node_modules");
  // Otherwise the two entries would race to copy the same files.
  assert.ok(web.filter?.includes("!node_modules"));
});

test("the backend is packaged where the shell looks for it", () => {
  const backend = build.extraResources.find((entry) => entry.from === ".build/backend");
  assert.ok(backend);
  assert.equal(backend.to, "backend");
});

test("packaging runs the runtime resource check", () => {
  assert.equal(build.afterPack, "./scripts/after-pack.cjs");
});
