"use strict";

// A slow cold launch must not consume the budget for assertions. Each phase
// has one fixed deadline; progress reports never extend it.
function readTimeout(value, fallback) {
  const timeout = value === undefined ? fallback : Number(value);
  if (!Number.isSafeInteger(timeout) || timeout <= 0 || timeout > 2147483647) {
    throw new Error(`Invalid browser timeout: ${value}`);
  }
  return timeout;
}

function createWatchdog(onTimeout, timers = {setTimeout, clearTimeout}) {
  let handle;
  return {
    start(phase, timeout) {
      this.stop();
      handle = timers.setTimeout(() => onTimeout({phase, timeout_ms: timeout}), timeout);
    },
    stop() {
      if (handle !== undefined) timers.clearTimeout(handle);
      handle = undefined;
    }
  };
}

module.exports = {readTimeout, createWatchdog};
