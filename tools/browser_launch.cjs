"use strict";
const {lstatSync, mkdtempSync, rmSync} = require("node:fs");
const {spawnSync} = require("node:child_process");
const {tmpdir} = require("node:os");
const {join} = require("node:path");

function createBrowserLaunchEnvironment(target, {platform = process.platform,
  environment = process.env, temporaryRoot = tmpdir(), lifecycle = process} = {}) {
  let directory, identity, exitCleanupRegistered = false;
  function directoryExists(path, expected) {
    const current = lstatSync(path, {throwIfNoEntry: false});
    if (!current) return false;
    if (!current.isDirectory() || current.dev !== expected.dev || current.ino !== expected.ino) {
      throw new Error("Firefox test home directory identity changed: " + path);
    }
    return true;
  }
  function native(command, args) {
    const result = spawnSync(command, args, {encoding: "utf8", timeout: 500, maxBuffer: 16384});
    if (result.error || result.status !== 0) {
      throw new Error("Firefox test home ACL command failed: " + command + ": " +
        (result.error?.message || result.stderr || result.status), {cause: result.error});
    }
    return result.stdout;
  }
  function removeHomeDeleteProtection() {
    if (!directoryExists(directory, identity)) return false;
    const identities = new Map();
    for (const name of ["Documents", "Downloads", "Library"]) {
      const child = join(directory, name);
      const stat = lstatSync(child, {throwIfNoEntry: false});
      if (stat?.isDirectory()) identities.set(child, stat);
    }
    const library = join(directory, "Library");
    if (identities.has(library)) {
      const support = join(library, "Application Support");
      const stat = lstatSync(support, {throwIfNoEntry: false});
      if (stat?.isDirectory()) identities.set(support, stat);
    }
    const candidates = [...identities.keys()];
    if (!candidates.length) return false;
    const listing = native("/bin/ls", ["-lde", ...candidates]);
    const protectedDirectories = [];
    let current;
    for (const line of listing.split("\n")) {
      const header = candidates.find(child => line.endsWith(" " + child));
      if (header) current = header;
      else if (current && /^\s*\d+: (?:group:everyone|everyone|ABCDEFAB-CDEF-ABCD-EFAB-CDEF0000000C) deny delete$/i.test(line)) {
        protectedDirectories.push(current);
      }
    }
    if (!protectedDirectories.length) return false;
    if (!directoryExists(directory, identity)) return false;
    for (const [child, expected] of identities) {
      if (!directoryExists(child, expected)) throw new Error("Firefox test home folder disappeared: " + child);
    }
    // macOS protects standard home folders with this ACL. Leave other ACLs
    // and symlink targets alone, including anything outside this test home.
    native("/bin/chmod", ["-h", "-a", "everyone deny delete", ...new Set(protectedDirectories)]);
    return true;
  }
  function cleanup() {
    if (directory && directoryExists(directory, identity)) {
      const options = {recursive: true, force: true, maxRetries: 3, retryDelay: 100};
      try { rmSync(directory, options); } catch (error) {
        if (!["ENOTEMPTY", "EPERM", "EACCES"].includes(error.code)) throw error;
        let repaired;
        try { repaired = removeHomeDeleteProtection(); } catch (cause) { error.cause = cause; throw error; }
        if (!repaired) throw error;
        if (directoryExists(directory, identity)) rmSync(directory, options);
      }
    }
    if (directory) {
      directory = undefined;
      identity = undefined;
    }
    if (exitCleanupRegistered) {
      lifecycle.off("exit", cleanupAtExit);
      exitCleanupRegistered = false;
    }
  }
  function cleanupAtExit() {
    try { cleanup(); } catch (error) {
      console.error("Firefox test home cleanup failed:", error);
      lifecycle.exitCode ||= 1;
    }
  }
  return {
    options() {
      if (target !== "firefox" || platform !== "darwin") return {};
      // CoreFoundation needs its own home; keep HOME and the parent untouched.
      if (!directory) {
        directory = mkdtempSync(join(temporaryRoot, "botw-firefox-home-"));
        identity = lstatSync(directory);
      }
      return {env: {...environment, CFFIXED_USER_HOME: directory}};
    },
    cleanup,
    cleanupOnExit() {
      if (!directory || exitCleanupRegistered) return;
      // Register after Playwright's synchronous child-kill hook. Forced exits
      // cannot await browser.close() or rely on an asynchronous finally block.
      lifecycle.once("exit", cleanupAtExit);
      exitCleanupRegistered = true;
    }
  };
}

module.exports = {createBrowserLaunchEnvironment};
