"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const {EventEmitter} = require("node:events");
const {spawnSync} = require("node:child_process");
const fs = require("node:fs");
const {tmpdir} = require("node:os");
const path = require("node:path");
const vm = require("node:vm");
const {createBrowserLaunchEnvironment} = require("../tools/browser_launch.cjs");
const {createWatchdog, readTimeout} = require("../tools/browser_watchdog.cjs");
const smoke = fs.readFileSync("tools/browser_smoke.js", "utf8");
const launchSource = fs.readFileSync("tools/browser_launch.cjs", "utf8");
const flush = () => new Promise(resolve => setImmediate(resolve));

function launchHelper(remove, errors = [], native = spawnSync) {
  const module = {exports: {}};
  vm.compileFunction(launchSource, ["require", "module", "process", "console"])(
    name => {
      if (name === "node:fs") return {...fs, rmSync: remove};
      if (name === "node:child_process") return {spawnSync: native};
      return require(name);
    }, module, process, {error(...args) { errors.push(args); }});
  return module.exports.createBrowserLaunchEnvironment;
}

function fixture(t) {
  const root = fs.mkdtempSync(path.join(tmpdir(), "botw-launch-test-"));
  t.after(() => fs.rmSync(root, {recursive: true, force: true}));
  const previousHome = path.join(root, "existing-cf-home");
  fs.mkdirSync(previousHome);
  fs.writeFileSync(path.join(previousHome, "sentinel"), "keep");
  const environment = Object.freeze({HOME: path.join(root, "parent-home"),
    CFFIXED_USER_HOME: previousHome, PATH: "unchanged-path", CUSTOM: "unchanged-value",
    BOTW_CHROMIUM_EXECUTABLE_PATH: "/synthetic/chromium"});
  return {root, previousHome, environment};
}

function runLauncher(t, target, platform, mode = "launch-failure", remove = fs.rmSync) {
  const f = fixture(t), lifecycle = new EventEmitter();
  const events = [], deadlines = [], pending = new Map();
  let sequence = 0, home, childKill;
  const timers = {
    setTimeout(callback, delay) { const id = ++sequence; pending.set(id, {callback, delay}); return id; },
    clearTimeout(id) { pending.delete(id); }
  };
  const launched = [], exits = [], errors = [], logs = [];
  const applicationPasses = ["success", "close-failure"].includes(mode);
  const createEnvironment = launchHelper((directory, options) => {
    if (applicationPasses) events.push("cleanup-start");
    remove(directory, options);
    if (applicationPasses) events.push("cleanup-finished");
  }, errors);
  const assertHomePresent = () => { if (home) assert(fs.existsSync(home)); };
  const browser = {async close() {
    events.push("close-start"); assertHomePresent();
    if (mode === "close-stall") return new Promise(() => {});
    if (mode === "close-failure") throw new Error("Synthetic close failure");
    await flush(); assertHomePresent(); events.push("close-finished");
    lifecycle.off("exit", childKill);
  }};
  const engines = Object.fromEntries(["chromium", "firefox", "webkit"].map(name => [name, {
    async launch(options) {
      launched.push({name, options}); home = options.env?.CFFIXED_USER_HOME;
      assertHomePresent();
      // Stand in for Playwright's synchronous process-exit child-kill hook.
      const kill = () => { assertHomePresent(); events.push("child-killed"); };
      childKill = kill;
      lifecycle.on("exit", kill);
      if (mode === "launch-stall") return new Promise(() => {});
      if (mode === "launch-failure") {
        events.push("launch-failed"); lifecycle.off("exit", kill);
        throw new Error("Synthetic launch failure");
      }
      return browser;
    }
  }]));
  const fakeProcess = Object.assign(lifecycle, {platform, env: f.environment,
    argv: ["node", "tools/browser_smoke.js", "http://fixture", target],
    exit(code) { exits.push(code); lifecycle.exitCode = code; lifecycle.emit("exit", code); }});
  const modules = {
    playwright: engines, "axe-core": {source: ""}, "node:fs/promises": {mkdir: async () => {}},
    "./browser_launch.cjs": {createBrowserLaunchEnvironment: name => createEnvironment(name,
      {platform, environment: f.environment, temporaryRoot: f.root, lifecycle})},
    "./browser_watchdog.cjs": {readTimeout, createWatchdog: callback => {
      const watchdog = createWatchdog(callback, timers);
      return {start(phase, timeout) { deadlines.push({phase, timeout}); watchdog.start(phase, timeout); },
        stop() { watchdog.stop(); }};
    }},
    "./browser_update_checks.cjs": {runBrowserUpdateChecks: async () => {
      if (mode === "update-stall") return new Promise(() => {});
      if (applicationPasses) return;
      throw new Error("Synthetic stop after launch");
    }},
    "./browser_storage_checks.cjs": {runBrowserStorageChecks: async () => {}}
  };
  const context = vm.createContext({process: fakeProcess, ...timers,
    require(name) { assert(name in modules, name); return modules[name]; },
    console: {log(value) {
      logs.push(JSON.parse(value));
      if (logs.at(-1).status === "ok") events.push("status:ok");
    }, error(value) { errors.push(value); }}});
  if (applicationPasses) {
    // Keep the real entry point and close path; stand in for the DOM checks.
    const entry = smoke.lastIndexOf("\n(async () => {");
    assert(entry > 0);
    vm.runInContext(smoke.slice(0, entry), context);
    context.runDesktop = async () => ({rendered: 2, manual: true, routes: true, dsu: true});
    for (const name of ["runResponsive", "runDisplayPreferences", "runLocalTimezone", "runBilingual"]) {
      context[name] = async () => {};
    }
    vm.runInContext(smoke.slice(entry), context);
  } else {
    vm.runInContext(smoke, context);
  }
  return {...f, launched, exits, events, deadlines, errors, logs, lifecycle,
    expire(delay) {
      const entry = [...pending].find(([, task]) => task.delay === delay);
      assert(entry, "Expected deadline " + delay);
      pending.delete(entry[0]); entry[1].callback();
    }};
}

for (const platform of ["darwin", "win32", "linux"]) {
  for (const target of ["firefox", "chromium", "webkit", "chrome", "edge"]) {
    test(`${platform}/${target}: only macOS Firefox gets a separate child environment`, async t => {
      const before = {...process.env};
      const f = runLauncher(t, target, platform);
      await flush();
      const [{name, options}] = f.launched;
      assert.equal(name, ["chrome", "edge"].includes(target) ? "chromium" : target);
      const expected = {headless: true};
      if (target === "chromium") expected.executablePath = f.environment.BOTW_CHROMIUM_EXECUTABLE_PATH;
      if (target === "chrome") expected.channel = "chrome";
      if (target === "edge") expected.channel = "msedge";
      if (platform === "darwin" && target === "firefox") {
        const home = options.env.CFFIXED_USER_HOME;
        assert.notEqual(home, f.previousHome);
        assert.equal(path.dirname(home), f.root);
        assert.notEqual(options.env, f.environment);
        assert.deepEqual({...options.env, CFFIXED_USER_HOME: f.previousHome}, f.environment);
        assert(!fs.existsSync(home), "Launch failure must clean its own directory");
        expected.env = options.env;
      }
      assert.deepEqual(JSON.parse(JSON.stringify(options)), expected);
      assert.deepEqual(f.exits, [1]);
      assert.equal(fs.readFileSync(path.join(f.previousHome, "sentinel"), "utf8"), "keep");
      assert.deepEqual({...process.env}, before);
    });
  }
}

test("each launch owns a fresh directory and cleanup is limited and idempotent", t => {
  const f = fixture(t), lifecycle = new EventEmitter();
  const options = {platform: "darwin", environment: f.environment, temporaryRoot: f.root, lifecycle};
  const first = createBrowserLaunchEnvironment("firefox", options);
  const second = createBrowserLaunchEnvironment("firefox", options);
  const a = first.options().env.CFFIXED_USER_HOME, b = second.options().env.CFFIXED_USER_HOME;
  assert.notEqual(a, b);
  first.cleanupOnExit(); first.cleanupOnExit();
  assert.equal(lifecycle.listenerCount("exit"), 1);
  first.cleanup(); first.cleanup();
  assert(!fs.existsSync(a)); assert(fs.existsSync(b));
  assert.equal(lifecycle.listenerCount("exit"), 0);
  second.cleanup();
  assert(fs.existsSync(f.previousHome)); assert(fs.existsSync(f.root));
});

test("normal cleanup waits for browser.close to finish", async t => {
  const f = runLauncher(t, "firefox", "darwin", "close");
  await flush(); await flush();
  assert.deepEqual(f.events, ["close-start", "close-finished"]);
  assert(!fs.existsSync(f.launched[0].options.env.CFFIXED_USER_HOME));
  assert.deepEqual(f.deadlines, [{phase: "launch", timeout: 90000},
    {phase: "update-regressions", timeout: 90000}, {phase: "close", timeout: 15000}]);
});

for (const [mode, phase] of [["launch-stall", "launch"], ["update-stall", "update-regressions"]]) {
  test(`${phase} watchdog exits at its original deadline and cleans after the child-kill hook`, async t => {
    const f = runLauncher(t, "firefox", "darwin", mode);
    await flush();
    const home = f.launched[0].options.env.CFFIXED_USER_HOME;
    assert(fs.existsSync(home));
    f.expire(90000);
    assert.deepEqual(f.exits, [124]);
    assert.deepEqual(f.events, ["child-killed"]);
    assert(!fs.existsSync(home));
    assert.equal(f.deadlines.at(-1).phase, phase);
    assert(fs.existsSync(f.previousHome));
  });
}

test("a stalled browser close keeps its directory until fatal-exit child shutdown", async t => {
  const f = runLauncher(t, "firefox", "darwin", "close-stall");
  await flush();
  const home = f.launched[0].options.env.CFFIXED_USER_HOME;
  assert(fs.existsSync(home));
  f.expire(10000); await flush();
  assert.deepEqual(f.exits, [1]);
  assert.deepEqual(f.events, ["close-start", "child-killed"]);
  assert(!fs.existsSync(home));
});

test("a real Node exit runs owned-directory cleanup after an earlier child-kill hook", t => {
  const f = fixture(t), record = path.join(f.root, "exit-order.json");
  const helper = require.resolve("../tools/browser_launch.cjs");
  const script = `
    const fs = require('node:fs');
    const {createBrowserLaunchEnvironment} = require(${JSON.stringify(helper)});
    const launch = createBrowserLaunchEnvironment('firefox', {
      platform: 'darwin', temporaryRoot: ${JSON.stringify(f.root)},
      environment: ${JSON.stringify(f.environment)}
    });
    const home = launch.options().env.CFFIXED_USER_HOME;
    process.once('exit', () => {
      if (!fs.existsSync(home)) throw Error('Cleanup ran before child shutdown');
      fs.writeFileSync(${JSON.stringify(record)}, JSON.stringify({home, childKillHookRan: true}));
    });
    launch.cleanupOnExit();
    process.exit(124);
  `;
  const result = spawnSync(process.execPath, ["-e", script], {encoding: "utf8", timeout: 10000});
  assert.equal(result.status, 124, result.stdout + result.stderr);
  const saved = JSON.parse(fs.readFileSync(record, "utf8"));
  assert.equal(saved.childKillHookRan, true);
  assert(!fs.existsSync(saved.home));
  assert(fs.existsSync(f.previousHome));
});

test("transient ENOTEMPTY recovery delegates bounded retries to Node", t => {
  const f = fixture(t), calls = [];
  const create = launchHelper((directory, options) => {
    calls.push({directory, options});
    // Model two transient failures inside rmSync, without retrying cleanup itself.
    if ((options.maxRetries ?? 0) < 2) throw Object.assign(new Error("Synthetic ENOTEMPTY"), {code: "ENOTEMPTY"});
    fs.rmSync(directory, options);
  });
  const launch = create("firefox", {platform: "darwin", environment: f.environment,
    temporaryRoot: f.root, lifecycle: new EventEmitter()});
  const home = launch.options().env.CFFIXED_USER_HOME;
  fs.writeFileSync(path.join(home, "synthetic-cache"), "temporary");
  launch.cleanup(); launch.cleanup();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].directory, home);
  assert.deepEqual({...calls[0].options}, {recursive: true, force: true, maxRetries: 3, retryDelay: 100});
  assert(!fs.existsSync(home));
  assert.equal(fs.readFileSync(path.join(f.previousHome, "sentinel"), "utf8"), "keep");
});

test("persistent removal failure retains ownership and the exit fallback until deletion succeeds", t => {
  const f = fixture(t), lifecycle = new EventEmitter(), calls = [], errors = [];
  let fail = true;
  const failure = Object.assign(new Error("Synthetic persistent ENOTEMPTY"), {code: "ENOTEMPTY"});
  const create = launchHelper((directory, options) => {
    calls.push(directory);
    if (fail) throw failure;
    fs.rmSync(directory, options);
  }, errors);
  const launch = create("firefox", {platform: "darwin", environment: f.environment,
    temporaryRoot: f.root, lifecycle});
  const sibling = fs.mkdtempSync(path.join(f.root, "botw-firefox-home-"));
  const home = launch.options().env.CFFIXED_USER_HOME;
  launch.cleanupOnExit();
  for (let attempt = 0; attempt < 2; attempt++) {
    assert.throws(() => launch.cleanup(), error => error === failure);
    assert.equal(launch.options().env.CFFIXED_USER_HOME, home);
    assert(fs.existsSync(home));
    assert.equal(lifecycle.listenerCount("exit"), 1);
  }
  lifecycle.emit("exit", 0);
  assert.equal(lifecycle.exitCode, 1);
  assert.equal(errors.length, 1);
  assert.equal(errors[0][1], failure);
  assert.equal(launch.options().env.CFFIXED_USER_HOME, home);
  fail = false;
  launch.cleanup(); launch.cleanup();
  assert.deepEqual(calls, [home, home, home, home]);
  assert(!fs.existsSync(home)); assert(fs.existsSync(sibling));
  assert.equal(fs.readFileSync(path.join(f.previousHome, "sentinel"), "utf8"), "keep");
  assert.equal(lifecycle.listenerCount("exit"), 0);
});

test("the final success report follows browser closure and owned-home removal", async t => {
  const f = runLauncher(t, "firefox", "darwin", "success");
  await flush(); await flush();
  assert.deepEqual(f.events, ["close-start", "close-finished", "cleanup-start", "cleanup-finished", "status:ok"]);
  assert.deepEqual(f.exits, []);
  assert.deepEqual(f.errors, []);
  assert.deepEqual(f.logs.filter(value => value.status === "ok"), [{status: "ok", browser: "firefox",
    rendered: 2, manual: true, routes: true, dsu: true, responsive: true, zoom_200: true,
    reduced_motion: true, local_timezone: true, bilingual: true, storage_recovery: true}]);
  assert(!fs.existsSync(f.launched[0].options.env.CFFIXED_USER_HOME));
});

for (const code of ["ENOTEMPTY", "EACCES"]) {
  test(`cleanup failure after application assertions fails the run without a success report (${code})`, async t => {
    const calls = [];
    const f = runLauncher(t, "firefox", "darwin", "success", directory => {
      calls.push(directory);
      throw Object.assign(new Error("Synthetic persistent ENOTEMPTY"), {code});
    });
    await flush(); await flush();
    const home = f.launched[0].options.env.CFFIXED_USER_HOME;
    assert.deepEqual(f.events, ["close-start", "close-finished", "cleanup-start", "cleanup-start"]);
    assert.deepEqual(calls, [home, home]);
    assert(fs.existsSync(home));
    assert.deepEqual(f.exits, [1]);
    assert.equal(f.lifecycle.exitCode, 1);
    assert.equal(f.errors.length, 2);
    assert.equal(f.errors[0].code, code);
    assert.equal(f.errors[1][0], "Firefox test home cleanup failed:");
    assert(!f.logs.some(value => value.status === "ok"));
  });
}

test("browser close failure after application assertions prevents a success report", async t => {
  const f = runLauncher(t, "firefox", "darwin", "close-failure");
  await flush(); await flush();
  assert.deepEqual(f.events, ["close-start", "child-killed", "cleanup-start", "cleanup-finished"]);
  assert.deepEqual(f.exits, [1]);
  assert(!f.logs.some(value => value.status === "ok"));
  assert(!fs.existsSync(f.launched[0].options.env.CFFIXED_USER_HOME));
});

for (const exitCode of [0, 124]) {
  test(`a real Node exit with persistent cleanup failure preserves failure status (initial ${exitCode})`, t => {
    const f = fixture(t), helper = require.resolve("../tools/browser_launch.cjs");
    const script = `
      const fs = require('node:fs');
      fs.rmSync = directory => { throw Object.assign(new Error('Synthetic persistent ENOTEMPTY'),
        {code: 'ENOTEMPTY', path: directory}); };
      const {createBrowserLaunchEnvironment} = require(${JSON.stringify(helper)});
      const launch = createBrowserLaunchEnvironment('firefox', {platform: 'darwin',
        temporaryRoot: ${JSON.stringify(f.root)}, environment: ${JSON.stringify(f.environment)}});
      console.log(launch.options().env.CFFIXED_USER_HOME);
      launch.cleanupOnExit();
      process.exit(${exitCode});
    `;
    const result = spawnSync(process.execPath, ["-e", script], {encoding: "utf8", timeout: 10000});
    assert.equal(result.status, exitCode || 1, result.stdout + result.stderr);
    assert.match(result.stderr, /Firefox test home cleanup failed:.*Synthetic persistent ENOTEMPTY/);
    const home = result.stdout.trim();
    assert.equal(fs.realpathSync(path.dirname(home)), fs.realpathSync(f.root));
    assert(fs.existsSync(home));
    assert(fs.existsSync(f.previousHome));
  });
}

function protectedHome(t, controls = {}) {
  const f = fixture(t), lifecycle = new EventEmitter(), calls = [], removals = [], errors = [];
  const failure = Object.assign(new Error("Synthetic protected home cleanup failure"), {code: controls.code ?? "ENOTEMPTY"});
  let repaired = false;
  const create = launchHelper((directory, options) => {
    removals.push({directory, options});
    if (!repaired || controls.persistent) throw failure;
    fs.rmSync(directory, options);
  }, errors, (command, args, options) => {
    calls.push({command, args, options});
    if (controls.fail === command) {
      return {status: 1, stderr: "Synthetic ACL command failure", error: controls.error};
    }
    if (command === "/bin/ls") {
      const stdout = args.slice(1).map(directory => "drwx------ 2 test staff 64 " + directory +
        "\n 0: " + (controls.acl ?? "ABCDEFAB-CDEF-ABCD-EFAB-CDEF0000000C deny delete")).join("\n");
      controls.afterListing?.();
      return {status: 0, stdout};
    }
    assert.equal(command, "/bin/chmod");
    repaired = true;
    return {status: 0, stdout: ""};
  });
  const launch = create("firefox", {platform: "darwin", environment: f.environment,
    temporaryRoot: f.root, lifecycle});
  const home = launch.options().env.CFFIXED_USER_HOME;
  const directories = ["Documents", "Downloads", "Library", path.join("Library", "Application Support")]
    .map(name => path.join(home, name));
  for (const directory of directories) fs.mkdirSync(directory, {recursive: true});
  return {...f, launch, home, directories, calls, removals, errors, lifecycle, failure};
}

for (const code of ["ENOTEMPTY", "EPERM", "EACCES"]) {
  test(`macOS protected-home recovery removes only the recognized delete ACL once (${code})`, t => {
    const f = protectedHome(t, {code});
    f.launch.cleanupOnExit();
    f.launch.cleanup(); f.launch.cleanup();
    assert.equal(f.calls.length, 2);
    assert.deepEqual(f.calls[0].args, ["-lde", ...f.directories]);
    assert.deepEqual(f.calls[1].args, ["-h", "-a", "everyone deny delete", ...f.directories]);
    for (const call of f.calls) {
      assert.equal(call.options.timeout, 500);
      assert.equal(call.options.maxBuffer, 16384);
    }
    assert.equal(f.removals.length, 2);
    for (const call of f.removals) {
      assert.equal(call.directory, f.home);
      assert.deepEqual({...call.options}, {recursive: true, force: true, maxRetries: 3, retryDelay: 100});
    }
    assert(!fs.existsSync(f.home)); assert(fs.existsSync(f.previousHome));
    assert.equal(f.lifecycle.listenerCount("exit"), 0);
  });
}

for (const acl of ["group:everyone allow read", "group:everyone deny delete,writeattr", "other deny delete"]) {
  test(`unrecognized home ACL is left intact: ${acl}`, t => {
    const f = protectedHome(t, {acl});
    assert.throws(() => f.launch.cleanup(), error => error === f.failure);
    assert.equal(f.calls.length, 1);
    assert.equal(f.calls[0].command, "/bin/ls");
    assert.equal(f.removals.length, 1);
    assert.equal(f.launch.options().env.CFFIXED_USER_HOME, f.home);
    assert(fs.existsSync(f.home));
  });
}

for (const code of ["ENOTEMPTY", "EACCES"]) {
  test(`home-folder symlinks and their targets are excluded from ACL changes (${code})`, t => {
    const f = protectedHome(t, {code});
    const library = path.join(f.home, "Library");
    fs.rmSync(path.join(f.home, "Documents"), {recursive: true});
    fs.rmSync(library, {recursive: true});
    fs.symlinkSync(f.previousHome, path.join(f.home, "Documents"), "junction");
    fs.symlinkSync(f.previousHome, library, "junction");
    f.launch.cleanup();
    assert.deepEqual(f.calls[0].args, ["-lde", path.join(f.home, "Downloads")]);
    assert.deepEqual(f.calls[1].args, ["-h", "-a", "everyone deny delete", path.join(f.home, "Downloads")]);
    assert.equal(fs.readFileSync(path.join(f.previousHome, "sentinel"), "utf8"), "keep");
  });
}

for (const replaced of ["root", "Library"]) {
  for (const code of ["ENOTEMPTY", "EACCES"]) {
    test(`a replaced ${replaced} directory is never removed or given different ACLs (${code})`, t => {
      const controls = {code}, f = protectedHome(t, controls);
      const target = replaced === "root" ? f.home : path.join(f.home, "Library");
      const saved = path.join(f.root, "retained-original");
      function replace() {
        fs.renameSync(target, saved);
        fs.mkdirSync(target);
        fs.writeFileSync(path.join(target, "foreign-sentinel"), "keep");
      }
      if (replaced === "root") replace();
      else controls.afterListing = replace;
      assert.throws(() => f.launch.cleanup(), error => /identity changed/.test(error.message) ||
        (error === f.failure && /identity changed/.test(error.cause?.message)));
      assert(!f.calls.some(call => call.command === "/bin/chmod"));
      assert.equal(fs.readFileSync(path.join(target, "foreign-sentinel"), "utf8"), "keep");
      assert.equal(f.launch.options().env.CFFIXED_USER_HOME, f.home);
    });
  }
}

for (const [command, error] of [["/bin/ls", undefined], ["/bin/ls", Object.assign(new Error("Synthetic timeout"), {code: "ETIMEDOUT"})], ["/bin/chmod", undefined]]) {
  test(`ACL command failure stays visible (${command}, ${error?.code || "status 1"})`, t => {
    const f = protectedHome(t, {fail: command, error});
    assert.throws(() => f.launch.cleanup(), failure => failure === f.failure &&
      /ACL command failed/.test(failure.cause.message));
    assert.equal(f.removals.length, 1);
    assert.equal(f.launch.options().env.CFFIXED_USER_HOME, f.home);
    assert(fs.existsSync(f.home));
  });
}

for (const code of ["ENOTEMPTY", "EACCES"]) {
  test(`persistent removal failure after ACL recovery fails without another recovery loop (${code})`, t => {
    const f = protectedHome(t, {persistent: true, code});
    assert.throws(() => f.launch.cleanup(), error => error === f.failure);
    assert.equal(f.removals.length, 2);
    assert.equal(f.calls.length, 2);
    assert.equal(f.launch.options().env.CFFIXED_USER_HOME, f.home);
    assert(fs.existsSync(f.home));
  });
}

for (const code of ["ENOTEMPTY", "EACCES"]) {
  test(`forced-exit cleanup can recover protected home folders after the child-kill hook (${code})`, t => {
    const f = protectedHome(t, {code}), events = [];
    f.lifecycle.exitCode = 124;
    f.lifecycle.once("exit", () => { assert(fs.existsSync(f.home)); events.push("child-killed"); });
    f.launch.cleanupOnExit();
    f.lifecycle.emit("exit", 124);
    assert.deepEqual(events, ["child-killed"]);
    assert.deepEqual(f.errors, []);
    assert.equal(f.lifecycle.exitCode, 124);
    assert(!fs.existsSync(f.home));
  });
}

test("EACCES without the recognized home ACL remains a visible owned-directory failure", t => {
  const f = protectedHome(t, {code: "EACCES", acl: "group:everyone allow read"});
  assert.throws(() => f.launch.cleanup(), error => error === f.failure);
  assert.equal(f.calls.length, 1);
  assert.equal(f.removals.length, 1);
  assert.equal(f.launch.options().env.CFFIXED_USER_HOME, f.home);
  assert(fs.existsSync(f.home));
});
