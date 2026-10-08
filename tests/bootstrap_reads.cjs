"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function setup(filename, fetch, timers = {setTimeout, clearTimeout}) {
  const source = fs.readFileSync(path.join(__dirname, "../botw_companion/web", filename), "utf8");
  const start = source.indexOf("async function fetchStartupJson(");
  assert.notEqual(start, -1);
  const context = vm.createContext({fetch, AbortController, documentLeaving: false, ...timers});
  vm.runInContext(source.slice(start, source.indexOf("async function loadRuntimePlatform(", start)), context);
  return context;
}

for (const filename of ["app.js", "app_en.js"]) {
  test(`${filename}: retries one failed GET and keeps the successful data`, async () => {
    let calls = 0;
    const c = setup(filename, async (url, options) => {
      assert.equal(url, "/api/manual"); assert.ok(options.signal);
      if (++calls === 1) throw new TypeError("Network failure");
      return {ok: true, json: async () => ({entries: {goal: {completed: true}}})};
    });
    const result = await c.fetchStartupJson("/api/manual");
    assert.equal(result.data.entries.goal.completed, true); assert.equal(calls, 2);
  });
  test(`${filename}: interrupted response bodies also get one retry`, async () => {
    let calls = 0;
    const c = setup(filename, async () => {
      const first = ++calls === 1;
      return {ok: true, json: async () => { if (first) throw new TypeError("Body interrupted"); return {ready: true}; }};
    });
    assert.equal((await c.fetchStartupJson("/api/report")).data.ready, true);
    assert.equal(calls, 2);
  });
  test(`${filename}: HTTP errors and invalid JSON are not hidden by retries`, async () => {
    let calls = 0;
    const c = setup(filename, async () => { calls++; return {ok: false, status: 403, json: async () => ({erreur: "Denied"})}; });
    assert.equal((await c.fetchStartupJson("/api/manual")).response.status, 403);
    assert.equal(calls, 1);
    const broken = setup(filename, async () => { calls++; return {json: async () => { throw new SyntaxError("Invalid JSON"); }}; });
    await assert.rejects(broken.fetchStartupJson("/api/manual"), /Invalid JSON/);
    assert.equal(calls, 2);
    const rejected = setup(filename, async () => {
      calls++; return {ok: false, status: 403, json: async () => { throw new TypeError("Rejected body interrupted"); }};
    });
    await assert.rejects(rejected.fetchStartupJson("/api/manual"), /Rejected body interrupted/);
    assert.equal(calls, 3);
  });
  test(`${filename}: permanent network failures stop after two attempts`, async () => {
    let calls = 0;
    const c = setup(filename, async () => { calls++; throw new TypeError("Still offline"); });
    await assert.rejects(c.fetchStartupJson("/api/manual"), /Still offline/);
    assert.equal(calls, 2);
  });
  test(`${filename}: stalled reads are aborted at the deadline`, async () => {
    let calls = 0, deadlines = [];
    const timers = {
      setTimeout(callback, delay) { deadlines.push(delay); return setTimeout(callback, 0); },
      clearTimeout
    };
    const c = setup(filename, async (_url, {signal}) => {
      calls++;
      return new Promise((_resolve, reject) => signal.addEventListener("abort", () => {
        const error = new Error("Read timed out"); error.name = "AbortError"; reject(error);
      }, {once: true}));
    }, timers);
    await assert.rejects(c.fetchStartupJson("/api/manual"), /Read timed out/);
    assert.equal(calls, 2); assert.deepEqual(deadlines, [10000, 250, 10000]);
  });
  test(`${filename}: a document being replaced does not restart its requests`, async () => {
    let calls = 0;
    const c = setup(filename, async () => { calls++; throw new TypeError("Leaving document"); });
    c.documentLeaving = true;
    await assert.rejects(c.fetchStartupJson("/api/manual"), /Leaving document/);
    assert.equal(calls, 1);
  });
  test(`${filename}: navigation during the retry pause cancels the next attempt`, async () => {
    let calls = 0, c;
    const timers = {
      setTimeout(callback, delay) {
        if (delay === 250) return setTimeout(() => { c.documentLeaving = true; callback(); }, 0);
        return setTimeout(callback, delay);
      }, clearTimeout
    };
    c = setup(filename, async () => { calls++; throw new TypeError("Navigation started"); }, timers);
    await assert.rejects(c.fetchStartupJson("/api/manual"), /Navigation started/);
    assert.equal(calls, 1);
  });
}
