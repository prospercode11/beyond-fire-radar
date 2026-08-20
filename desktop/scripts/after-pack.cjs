"use strict";

// electron-builder afterPack hook: refuse to build an installer around a
// packaged directory that is missing the dashboard or the backend.

const { verifyStructure } = require("./verify-package.cjs");

exports.default = async function afterPack(context) {
  verifyStructure(context.appOutDir);
  console.log(`after-pack: verified runtime resources in ${context.appOutDir}`);
};
