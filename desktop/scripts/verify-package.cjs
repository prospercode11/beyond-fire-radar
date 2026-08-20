"use strict";

// Verifies that a packaged application directory really contains the bundled
// dashboard and backend.
//
// electron-builder reports a missing extraResources directory as a warning and
// still produces an installer, so packaging alone proves nothing. This check is
// wired into afterPack and is also run against release/win-unpacked in CI.

const { spawn } = require("node:child_process");
const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");
const {
  missingRuntimeResources,
  runtimeResourcePaths,
} = require("../runtime.cjs");

const BOOT_TIMEOUT_MS = 120000;

function platformForPackage(packageDirectory) {
  return fs.existsSync(path.join(packageDirectory, "Beyond Fire Radar.exe")) ? "win32" : process.platform;
}

function resourcesPathFor(packageDirectory, platform) {
  return platform === "darwin" && !fs.existsSync(path.join(packageDirectory, "resources"))
    ? path.join(packageDirectory, "Beyond Fire Radar.app", "Contents", "Resources")
    : path.join(packageDirectory, "resources");
}

function verifyStructure(packageDirectory) {
  const platform = platformForPackage(packageDirectory);
  const resourcesPath = resourcesPathFor(packageDirectory, platform);
  const resourcePaths = runtimeResourcePaths(resourcesPath, platform);
  const missing = missingRuntimeResources(resourcePaths, (target) => fs.existsSync(target));
  if (missing.length > 0) {
    const details = missing.map((entry) => `  ${entry.label}: ${entry.path}`).join("\n");
    throw new Error(
      `The packaged application is missing required runtime resources:\n${details}\n` +
        'Run "npm run prepare:web" and "npm run build:backend" before packaging.',
    );
  }
  return { platform, resourcePaths };
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

async function waitForUrl(url, child, deadline) {
  let lastError = "no response";
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`the packaged web server exited with ${child.exitCode}`);
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (response.ok) return;
      lastError = `HTTP ${response.status}`;
    } catch (error) {
      lastError = error.message;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`the packaged web server never served ${url} (${lastError})`);
}

// Runs the packaged server.js exactly as the desktop shell does, so a tree that
// is present but unusable fails here instead of on a client machine.
async function verifyBoot(resourcePaths) {
  const port = await findFreePort();
  const environment = { ...process.env, HOSTNAME: "127.0.0.1", PORT: String(port), NODE_ENV: "production" };
  delete environment.ELECTRON_RUN_AS_NODE;
  const child = spawn(process.execPath, [resourcePaths.webServer], {
    cwd: resourcePaths.webDirectory,
    env: environment,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const output = [];
  child.stdout.on("data", (chunk) => output.push(String(chunk)));
  child.stderr.on("data", (chunk) => output.push(String(chunk)));
  try {
    await waitForUrl(`http://127.0.0.1:${port}/`, child, Date.now() + BOOT_TIMEOUT_MS);
    console.log(`verify-package: packaged dashboard served http://127.0.0.1:${port}/`);
  } catch (error) {
    if (output.length > 0) process.stderr.write(`${output.join("")}\n`);
    throw error;
  } finally {
    if (child.exitCode === null) child.kill();
  }
}

async function main() {
  const argv = process.argv.slice(2);
  const directoryFlag = argv.indexOf("--dir");
  const packageDirectory = path.resolve(
    directoryFlag === -1 ? path.join(__dirname, "..", "release", "win-unpacked") : argv[directoryFlag + 1],
  );
  if (!fs.existsSync(packageDirectory)) {
    throw new Error(`no packaged application directory at ${packageDirectory}`);
  }
  const { resourcePaths } = verifyStructure(packageDirectory);
  console.log(`verify-package: runtime resources present in ${packageDirectory}`);
  if (argv.includes("--boot")) await verifyBoot(resourcePaths);
}

module.exports = { verifyStructure };

if (require.main === module) {
  main().catch((error) => {
    process.stderr.write(`verify-package: ${error.message}\n`);
    process.exit(1);
  });
}
