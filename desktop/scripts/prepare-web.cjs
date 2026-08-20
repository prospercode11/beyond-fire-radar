"use strict";

// Builds the Next.js dashboard and normalizes the standalone output into
// desktop/.build/web, the directory packaged as resources/web.
//
// The Next.js CLI is started through the current Node/Electron executable
// instead of `npm`. Windows resolves `npm` to `npm.cmd`, and Node refuses to
// spawn a .cmd file without a shell, so an `npm` spawn here fails with EINVAL
// on Windows while succeeding on macOS and Linux.

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const desktopRoot = path.resolve(__dirname, "..");
const repositoryRoot = path.resolve(desktopRoot, "..");
const webRoot = path.join(repositoryRoot, "apps", "web");
const buildRoot = path.join(desktopRoot, ".build", "web");
const MAX_STANDALONE_SEARCH_DEPTH = 4;

function fail(message) {
  throw new Error(message);
}

function resolveNextCli(webRoot) {
  try {
    return require.resolve("next/dist/bin/next", { paths: [webRoot] });
  } catch {
    return fail(
      `cannot resolve the Next.js CLI from ${webRoot}. Run "npm ci --prefix apps/web" first.`,
    );
  }
}

function buildWeb(webRoot) {
  const cli = resolveNextCli(webRoot);
  const environment = { ...process.env };
  // The packaged dashboard proxies API calls to the bundled backend port.
  environment.API_PROXY_TARGET = "http://127.0.0.1:28741";
  environment.NODE_ENV = "production";
  // Set when Electron runs a script as Node; the Next.js CLI must not inherit it.
  delete environment.ELECTRON_RUN_AS_NODE;
  const build = spawnSync(process.execPath, [cli, "build"], {
    cwd: webRoot,
    env: environment,
    stdio: "inherit",
  });
  if (build.error) fail(`the Next.js build could not be started: ${build.error.message}`);
  if (build.signal) fail(`the Next.js build was terminated by signal ${build.signal}`);
  if (build.status !== 0) fail(`the Next.js build exited with code ${build.status}`);
}

// A standalone build emits server.js at its root for a single-package project and
// under the package path (apps/web/server.js) when Next infers a workspace root.
function findStandaloneEntryDirectory(standalone) {
  const queue = [{ directory: standalone, depth: 0 }];
  while (queue.length > 0) {
    const { directory, depth } = queue.shift();
    if (fs.existsSync(path.join(directory, "server.js"))) return directory;
    if (depth >= MAX_STANDALONE_SEARCH_DEPTH) continue;
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      if (!entry.isDirectory() || entry.name === "node_modules" || entry.name === ".next") continue;
      queue.push({ directory: path.join(directory, entry.name), depth: depth + 1 });
    }
  }
  return null;
}

// Flatten the standalone tree so server.js always sits at the root of the
// packaged directory, whichever layout Next.js produced.
function collectStandalone({ standalone, entryDirectory, webRoot, buildRoot }) {
  fs.rmSync(buildRoot, { recursive: true, force: true });
  fs.mkdirSync(buildRoot, { recursive: true });
  fs.cpSync(entryDirectory, buildRoot, { recursive: true });

  if (path.resolve(entryDirectory) !== path.resolve(standalone)) {
    const nestedRoot = path.relative(standalone, entryDirectory).split(path.sep)[0];
    for (const entry of fs.readdirSync(standalone, { withFileTypes: true })) {
      if (entry.name === nestedRoot) continue;
      fs.cpSync(path.join(standalone, entry.name), path.join(buildRoot, entry.name), {
        recursive: true,
        force: false,
        errorOnExist: false,
      });
    }
  }

  fs.cpSync(path.join(webRoot, ".next", "static"), path.join(buildRoot, ".next", "static"), {
    recursive: true,
  });
  const publicDirectory = path.join(webRoot, "public");
  if (fs.existsSync(publicDirectory)) {
    fs.cpSync(publicDirectory, path.join(buildRoot, "public"), { recursive: true });
  }
}

function countFiles(directory) {
  let total = 0;
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    total += entry.isDirectory() ? countFiles(path.join(directory, entry.name)) : 1;
  }
  return total;
}

function verifyPreparedRuntime(buildRoot) {
  const required = [
    ["dashboard server", path.join(buildRoot, "server.js")],
    ["browser assets", path.join(buildRoot, ".next", "static")],
    ["server manifest", path.join(buildRoot, ".next", "required-server-files.json")],
    ["Next.js dependency", path.join(buildRoot, "node_modules", "next")],
  ];
  const missing = required.filter(([, target]) => !fs.existsSync(target));
  if (missing.length > 0) {
    fail(
      `the prepared web runtime is incomplete:\n${missing
        .map(([label, target]) => `  ${label}: ${target}`)
        .join("\n")}`,
    );
  }
  if (countFiles(path.join(buildRoot, ".next", "static")) === 0) {
    fail(`no browser assets were copied into ${path.join(buildRoot, ".next", "static")}`);
  }
}

function main() {
  buildWeb(webRoot);

  const standalone = path.join(webRoot, ".next", "standalone");
  if (!fs.existsSync(standalone)) {
    fail(
      `the Next.js build produced no standalone output at ${standalone}. ` +
        'apps/web/next.config.ts must keep output: "standalone".',
    );
  }
  const entryDirectory = findStandaloneEntryDirectory(standalone);
  if (!entryDirectory) fail(`no standalone server.js was found under ${standalone}`);

  collectStandalone({ standalone, entryDirectory, webRoot, buildRoot });
  verifyPreparedRuntime(buildRoot);

  console.log(
    `prepare-web: prepared ${countFiles(buildRoot)} files at ${buildRoot} ` +
      `(standalone entry: ${path.relative(standalone, entryDirectory) || "."})`,
  );
}

module.exports = {
  collectStandalone,
  countFiles,
  findStandaloneEntryDirectory,
  verifyPreparedRuntime,
};

if (require.main === module) {
  try {
    main();
  } catch (error) {
    process.stderr.write(`prepare-web: ${error.message}\n`);
    process.exit(1);
  }
}
