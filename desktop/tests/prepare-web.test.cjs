"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const {
  collectStandalone,
  findStandaloneEntryDirectory,
  verifyPreparedRuntime,
} = require("../scripts/prepare-web.cjs");

function write(target, contents) {
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, contents, "utf8");
}

// Builds the two standalone layouts Next.js produces: server.js at the root when
// the traced root is apps/web, and server.js under the package path when Next
// infers a workspace root above it.
function buildFixture(nested) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "bfr-prepare-web-"));
  const webRoot = path.join(root, "apps", "web");
  const standalone = path.join(webRoot, ".next", "standalone");
  const appRoot = nested ? path.join(standalone, "apps", "web") : standalone;
  write(path.join(appRoot, "server.js"), "// standalone entry\n");
  write(path.join(appRoot, "package.json"), '{"name":"beyond-fire-radar-web"}\n');
  write(path.join(appRoot, ".next", "required-server-files.json"), "{}\n");
  write(path.join(appRoot, ".next", "server", "app", "page.js"), "// page\n");
  write(path.join(standalone, "node_modules", "next", "package.json"), '{"name":"next"}\n');
  write(path.join(webRoot, ".next", "static", "chunks", "main.js"), "// chunk\n");
  write(path.join(webRoot, "public", "logo.svg"), "<svg/>\n");
  return { root, webRoot, standalone, buildRoot: path.join(root, "desktop", ".build", "web") };
}

for (const nested of [false, true]) {
  const label = nested ? "workspace-nested" : "package-root";
  test(`a ${label} standalone build is flattened into a packageable runtime`, (t) => {
    const fixture = buildFixture(nested);
    t.after(() => fs.rmSync(fixture.root, { recursive: true, force: true }));

    const entryDirectory = findStandaloneEntryDirectory(fixture.standalone);
    assert.equal(
      path.relative(fixture.standalone, entryDirectory),
      nested ? path.join("apps", "web") : "",
    );

    collectStandalone({
      standalone: fixture.standalone,
      entryDirectory,
      webRoot: fixture.webRoot,
      buildRoot: fixture.buildRoot,
    });

    // The desktop shell always launches resources/web/server.js.
    assert.ok(fs.existsSync(path.join(fixture.buildRoot, "server.js")));
    assert.ok(fs.existsSync(path.join(fixture.buildRoot, ".next", "required-server-files.json")));
    assert.ok(fs.existsSync(path.join(fixture.buildRoot, ".next", "server", "app", "page.js")));
    assert.ok(fs.existsSync(path.join(fixture.buildRoot, ".next", "static", "chunks", "main.js")));
    assert.ok(fs.existsSync(path.join(fixture.buildRoot, "node_modules", "next", "package.json")));
    assert.ok(fs.existsSync(path.join(fixture.buildRoot, "public", "logo.svg")));

    verifyPreparedRuntime(fixture.buildRoot);
  });
}

test("verification rejects a runtime that is missing the dashboard server", (t) => {
  const fixture = buildFixture(false);
  t.after(() => fs.rmSync(fixture.root, { recursive: true, force: true }));
  collectStandalone({
    standalone: fixture.standalone,
    entryDirectory: fixture.standalone,
    webRoot: fixture.webRoot,
    buildRoot: fixture.buildRoot,
  });
  fs.rmSync(path.join(fixture.buildRoot, "server.js"));
  assert.throws(() => verifyPreparedRuntime(fixture.buildRoot), /dashboard server/);
});

test("verification rejects a runtime with no browser assets", (t) => {
  const fixture = buildFixture(false);
  t.after(() => fs.rmSync(fixture.root, { recursive: true, force: true }));
  collectStandalone({
    standalone: fixture.standalone,
    entryDirectory: fixture.standalone,
    webRoot: fixture.webRoot,
    buildRoot: fixture.buildRoot,
  });
  fs.rmSync(path.join(fixture.buildRoot, ".next", "static"), { recursive: true });
  fs.mkdirSync(path.join(fixture.buildRoot, ".next", "static"));
  assert.throws(() => verifyPreparedRuntime(fixture.buildRoot), /no browser assets/);
});
