"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const available = {update_available: true, latest_version: "9.8.7", status: "update_available"};
const reply = data => ({ok: true, json: async () => data});

function setup(filename, fetch, timers = {setTimeout, clearTimeout}) {
  const source = fs.readFileSync(path.join(__dirname, "../botw_companion/web", filename), "utf8");
  const actions = source.slice(source.indexOf("async function checkForUpdates("), source.indexOf("function loadRouteState("));
  const button = {disabled: false}, shown = [], messages = [];
  const context = vm.createContext({fetch, AbortController, UPDATE_CHECK_TIMEOUT_MS: 45000,
    ...timers, $: () => button, showAvailableUpdate: (data, manual) => shown.push({data, manual}),
    toast: (...args) => messages.push(args)});
  vm.runInContext(actions, context);
  return {context, button, shown, messages};
}

for (const filename of ["app.js", "app_en.js"]) {
  test(`${filename}: automatic detection survives one interrupted request`, async () => {
    let calls = 0;
    const s = setup(filename, async url => {
      assert.equal(url, "/api/update");
      if (++calls === 1) throw new TypeError("Connection interrupted");
      return reply(available);
    });
    await s.context.checkForUpdates(false);
    assert.equal(calls, 2); assert.equal(s.shown.length, 1);
    assert.equal(s.shown[0].manual, false); assert.equal(s.messages.length, 0);
  });
  test(`${filename}: manual detection retries safely and releases the button`, async () => {
    let calls = 0;
    const s = setup(filename, async url => {
      assert.equal(url, "/api/update?force=1");
      if (++calls === 1) throw new TypeError("Interrupted");
      return reply(available);
    });
    await s.context.checkForUpdates(true);
    assert.equal(calls, 2); assert.equal(s.shown[0].manual, true);
    assert.equal(s.button.disabled, false);
  });
  test(`${filename}: interrupted JSON bodies get one retry`, async () => {
    let calls = 0;
    const s = setup(filename, async () => {
      const first = ++calls === 1;
      return {ok: true, json: async () => { if (first) throw new TypeError("Body interrupted"); return available; }};
    });
    await s.context.checkForUpdates(); assert.equal(calls, 2); assert.equal(s.shown.length, 1);
  });
  test(`${filename}: HTTP errors and invalid JSON are not retried`, async () => {
    for (const response of [{ok: false}, reply(null), {ok: true, json: async () => { throw new SyntaxError("Invalid JSON"); }}]) {
      let calls = 0;
      const s = setup(filename, async () => { calls++; return response; });
      await s.context.checkForUpdates(true);
      assert.equal(calls, 1); assert.equal(s.shown.length, 0);
      assert.equal(s.messages.length, 1); assert.equal(s.button.disabled, false);
    }
  });
  test(`${filename}: permanent offline failure stops after two attempts`, async () => {
    for (const manual of [false, true]) {
      let calls = 0;
      const s = setup(filename, async () => { calls++; throw new TypeError("Offline"); });
      await s.context.checkForUpdates(manual);
      assert.equal(calls, 2); assert.equal(s.shown.length, 0);
      assert.equal(s.messages.length, manual ? 1 : 0); assert.equal(s.button.disabled, false);
    }
  });
  test(`${filename}: one deadline covers both attempts and a stall is aborted`, async () => {
    let calls = 0, deadlines = [];
    const timers = {setTimeout(callback, delay) {
      deadlines.push(delay); return setTimeout(callback, delay === 45000 ? 0 : delay);
    }, clearTimeout};
    const s = setup(filename, async (_url, {signal}) => {
      calls++;
      return new Promise((_resolve, reject) => signal.addEventListener("abort", () => {
        const error = new Error("Deadline expired"); error.name = "AbortError"; reject(error);
      }, {once: true}));
    }, timers);
    await s.context.checkForUpdates(true);
    assert.equal(calls, 1); assert.deepEqual(deadlines, [45000]);
    assert.equal(s.button.disabled, false); assert.equal(s.messages.length, 1);
  });
  test(`${filename}: expiry during the retry pause prevents another request`, async () => {
    let calls = 0, deadlines = [];
    const timers = {setTimeout(callback, delay) {
      deadlines.push(delay); return setTimeout(callback, delay === 45000 ? 0 : 10);
    }, clearTimeout};
    const s = setup(filename, async () => { calls++; throw new TypeError("Connection interrupted"); }, timers);
    await s.context.checkForUpdates(true);
    assert.equal(calls, 1); assert.deepEqual(deadlines, [45000, 250]);
    assert.equal(s.button.disabled, false); assert.equal(s.messages.length, 1);
  });
}
