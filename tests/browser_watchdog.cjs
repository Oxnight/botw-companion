"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const {createWatchdog, readTimeout} = require("../tools/browser_watchdog.cjs");

function fixture() {
  let now = 0, next = 0;
  const pending = new Map(), timeouts = [];
  const timers = {
    setTimeout(callback, delay) { const id = ++next; pending.set(id, {callback, deadline: now + delay}); return id; },
    clearTimeout(id) { pending.delete(id); }
  };
  return {
    watchdog: createWatchdog(value => timeouts.push(value), timers), timeouts,
    advance(ms) {
      now += ms;
      for (const [id, task] of pending) {
        if (task.deadline <= now) { pending.delete(id); task.callback(); }
      }
    }
  };
}

test("cold Chrome launch and browser checks do not consume the assertion budget", () => {
  const f = fixture();
  f.watchdog.start("launch", 90000); f.advance(50000);
  f.watchdog.start("update-regressions", 90000); f.advance(26000);
  f.watchdog.start("application", 120000); f.advance(65000);
  assert.deepEqual(f.timeouts, []);
  f.watchdog.stop(); f.advance(300000);
  assert.deepEqual(f.timeouts, []);
});

for (const [phase, timeout] of [["launch", 90000], ["update-regressions", 90000], ["application", 120000], ["close", 15000]]) {
  test(`a stalled ${phase} phase still expires at its fixed deadline`, () => {
    const f = fixture(); f.watchdog.start(phase, timeout);
    f.advance(timeout - 1); assert.deepEqual(f.timeouts, []);
    f.advance(1); assert.deepEqual(f.timeouts, [{phase, timeout_ms: timeout}]);
    f.watchdog.stop();
  });
}

test("invalid environment overrides cannot disable the watchdog", () => {
  assert.equal(readTimeout(undefined, 120000), 120000);
  assert.equal(readTimeout("180000", 120000), 180000);
  for (const value of ["", "0", "-1", "NaN", "Infinity", "1.5", "2147483648"]) {
    assert.throws(() => readTimeout(value, 120000), /Invalid browser timeout/);
  }
});
