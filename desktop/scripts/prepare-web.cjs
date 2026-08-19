"use strict";

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const desktopRoot = path.resolve(__dirname, "..");
const repositoryRoot = path.resolve(desktopRoot, "..");
const webRoot = path.join(repositoryRoot, "apps", "web");
const buildRoot = path.join(desktopRoot, ".build", "web");

const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
const build = spawnSync(npmCommand, ["run", "build"], {
  cwd: webRoot,
  env: {
    ...process.env,
    API_PROXY_TARGET: "http://127.0.0.1:28741",
  },
  stdio: "inherit",
});
if (build.status !== 0) process.exit(build.status ?? 1);

const standalone = path.join(webRoot, ".next", "standalone");
if (!fs.existsSync(path.join(standalone, "server.js"))) {
  throw new Error("Next.js standalone server was not produced.");
}
fs.rmSync(buildRoot, { recursive: true, force: true });
fs.mkdirSync(buildRoot, { recursive: true });
fs.cpSync(standalone, buildRoot, { recursive: true });
fs.cpSync(path.join(webRoot, ".next", "static"), path.join(buildRoot, ".next", "static"), {
  recursive: true,
});
const publicDirectory = path.join(webRoot, "public");
if (fs.existsSync(publicDirectory)) {
  fs.cpSync(publicDirectory, path.join(buildRoot, "public"), { recursive: true });
}
console.log(`Prepared standalone web runtime at ${buildRoot}`);
