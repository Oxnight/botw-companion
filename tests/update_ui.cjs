"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {test} = require("node:test");
const source = fs.readFileSync(path.join(__dirname, "../botw_companion/web/app.js"), "utf8");
const actions = source.slice(source.indexOf("async function installVerifiedUpdate("),
  source.indexOf("async function checkForUpdates("));

function setup(fetch, confirm = () => true) {
  const button = {disabled: false, textContent: "Installer et redémarrer"};
  const progress = {textContent: ""};
  const context = vm.createContext({
    fetch, confirm, clearTimeout() {}, updateDownloadTimer: null,
    updatePrimaryBusy: false, updateInstallationPending: false,
    runtimePlatform: {id: "macos"},
    $: id => id === "#downloadUpdate" ? button : progress,
    toast() {}, refreshUpdateDownload: async () => {}, startUpdateDownload: async () => {},
  });
  vm.runInContext(actions, context);
  return {context, button};
}

test("repeated clicks cannot launch two installations while the first request is pending", async () => {
  let release, installations = 0;
  const {context, button} = setup(async url => {
    if (url === "/api/update/download") {
      return {ok: true, json: async () => ({status: "ready_to_install", can_install: true})};
    }
    installations++;
    return new Promise(resolve => {release = () => resolve({ok: true, json: async () => ({})});});
  });
  const first = vm.runInContext("handleUpdatePrimaryAction()", context);
  await new Promise(resolve => setImmediate(resolve));
  await vm.runInContext("handleUpdatePrimaryAction()", context);
  assert.equal(installations, 1);
  assert.equal(button.disabled, true);
  release();
  await first;
  await vm.runInContext("handleUpdatePrimaryAction()", context);
  assert.equal(installations, 1);
  assert.equal(context.updateInstallationPending, true);
});

test("a refused handoff enables retry without leaving the installation pending", async () => {
  const {context, button} = setup(async () => ({ok: false, json: async () => ({erreur: "retry"})}));
  assert.equal(await vm.runInContext("installVerifiedUpdate()", context), false);
  assert.equal(context.updateInstallationPending, false);
  assert.equal(button.disabled, false);
});

test("cancelling confirmation does not stop the application or request installation", async () => {
  const {context} = setup(async () => assert.fail("No request after cancellation"), () => false);
  assert.equal(await vm.runInContext("installVerifiedUpdate()", context), false);
  assert.equal(context.updateInstallationPending, false);
});
