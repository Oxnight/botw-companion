"use strict";
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {test} = require('node:test');
const acorn = require('acorn');

const application = fs.readFileSync(path.join(__dirname, '../botw_companion/web/app.js'), 'utf8');
const smoke = fs.readFileSync(path.join(__dirname, '../tools/browser_smoke.js'), 'utf8');
const appTree = acorn.parse(application, {ecmaVersion: 'latest'});
const smokeTree = acorn.parse(smoke, {ecmaVersion: 'latest'});
function find(node, predicate) {
  if (!node || typeof node !== 'object') return;
  if (predicate(node)) return node;
  for (const value of Object.values(node)) {
    const found = Array.isArray(value)
      ? value.map(child => find(child, predicate)).find(Boolean) : find(value, predicate);
    if (found) return found;
  }
}
const roundTrip = find(smokeTree, node => node.type === 'VariableDeclarator' && node.id.name === 'routesRoundTrip').init.argument;
const clone = value => JSON.parse(JSON.stringify(value));
const turn = () => new Promise(resolve => setImmediate(resolve));
function deferred() {
  let resolve;
  const promise = new Promise(done => {resolve = done;});
  return {promise, resolve};
}

async function fixture(options = {}) {
  const release = deferred(), started = deferred(), committed = deferred();
  const requests = [], trace = [], timers = new Map();
  let sequence = 0, puts = 0;
  let store = {schema_version: 3, revision: 1, updated_at: 'saved-1',
    active_session_id: 'session-existing', sessions: {'session-existing': {
      id: 'session-existing', name: 'Private original route', start: null, strategy: 'distance',
      entries: [{tracking_id: 'synthetic:point', locked: true, snapshot: {name: 'Private point', x: 1, z: 2}}],
      created_at: 'created', updated_at: 'saved-1'}}};
  const response = (status, body) => ({status, ok: status >= 200 && status < 300, json: async () => clone(body)});
  const publish = incoming => {
    store = {...clone(incoming), revision: store.revision + 1, updated_at: 'saved-' + (store.revision + 1)};
    for (const session of Object.values(store.sessions)) {
      session.updated_at = store.updated_at;
      for (const entry of session.entries) {
        entry.snapshot = Object.fromEntries(Object.entries(entry.snapshot).filter(([, value]) => value !== null));
      }
    }
    return clone(store);
  };
  const conflict = () => response(409, {erreur: 'Les itinéraires ont changé dans une autre fenêtre; actualise puis réessaie'});
  const context = vm.createContext({AbortController, FETCH_TIMEOUT_MS: 10000, sessionCount: 1,
    crypto: {randomUUID: () => 'created'}, BOTWI18n: {t: () => 'Private new route'},
    browserStorage: {removeItem() {}}, ROUTE_STORAGE_KEY: 'test-route', toast() {}, renderItems() {},
    renderRoute() {context.optionCount = Object.keys(vm.runInContext('routesData.sessions', context)).length;},
    setTimeout(callback, delay) {timers.set(++sequence, {callback, delay}); return sequence;},
    clearTimeout(id) {timers.delete(id);},
    async fetch(url, settings = {}) {
      const method = settings.method || 'GET';
      requests.push({url, method});
      if (method === 'PUT') {
        const input = JSON.parse(settings.body);
        if (++puts === 1) {started.resolve(); await release.promise;}
        if (options.failSave) {committed.resolve(); return response(500, {erreur: 'Synthetic save failure'});}
        if (input.expected_revision !== store.revision) return conflict();
        const saved = publish(input.routes);
        trace.push({operation: 'save', revision: saved.revision});
        committed.resolve();
        return response(200, saved);
      }
      if (url === '/api/routes/export') {
        if (options.exportStatus) return response(options.exportStatus, {erreur: 'Synthetic export failure'});
        const exported = clone(store);
        trace.push({operation: 'export', revision: exported.revision, sessionCount: Object.keys(exported.sessions).length});
        // Force a save to commit after the GET snapshot and before the POST.
        if (options.commitAfterExport) {release.resolve(); await committed.promise;}
        if (options.wrongActive) exported.active_session_id = 'session-existing';
        return response(200, exported);
      }
      assert.equal(url, '/api/routes/import');
      const input = JSON.parse(settings.body);
      if (options.concurrentWriter) publish(store);
      if (input.expected_revision !== store.revision) {
        trace.push({operation: 'import', status: 409, expectedRevision: input.expected_revision, actualRevision: store.revision});
        return conflict();
      }
      const imported = clone(input.session);
      imported.id = 'session-imported';
      const saved = clone(store);
      saved.sessions[imported.id] = imported;
      saved.active_session_id = imported.id;
      const result = publish(saved);
      trace.push({operation: 'import', status: 200, revision: result.revision});
      if (options.corruptImport) result.sessions[imported.id].name = 'Incorrect imported content';
      if (options.corruptExisting) result.sessions['session-existing'].entries = [];
      return response(200, result);
    }});
  context.initial = clone(store);
  if (options.nullSnapshotFields) {
    Object.assign(context.initial.sessions['session-existing'].entries[0].snapshot, {category: null, content_origin: null});
  }
  vm.runInContext('let routesData = initial; let routeState = routesData.sessions[initial.active_session_id]; let routeSaveQueue = Promise.resolve();', context);
  for (const name of ['saveRouteState', 'routeSessionTemplate', 'createRouteSession']) {
    const node = appTree.body.find(node => node.type === 'FunctionDeclaration' && node.id.name === name);
    vm.runInContext(application.slice(node.start, node.end), context);
  }
  vm.runInContext('saveRouteState()', context);
  await started.promise;
  vm.runInContext('createRouteSession()', context);
  assert.equal(context.optionCount, 2);
  const evaluate = () => vm.runInContext('(' + smoke.slice(roundTrip.arguments[0].start, roundTrip.arguments[0].end) + ')(' +
    smoke.slice(roundTrip.arguments[1].start, roundTrip.arguments[1].end) + ')', context);
  return {evaluate, release: release.resolve, requests, trace, timers,
    settled: () => vm.runInContext('routeSaveQueue', context), store: () => clone(store)};
}

test('route export waits for every queued save despite immediate DOM updates', async () => {
  const f = await fixture();
  const result = f.evaluate();
  try {
    await turn();
    assert.equal(f.requests.filter(request => request.method === 'GET').length, 0,
      'The DOM option does not acknowledge route persistence');
  } finally {f.release();}
  const value = await result;
  assert.equal(value.ok, true, JSON.stringify(value));
  assert.equal(Object.keys(f.store().sessions).length, 3);
  assert.equal(f.timers.size, 0);
});

test('a delayed save cannot invalidate the export revision used by import', async t => {
  const f = await fixture({commitAfterExport: true});
  const result = f.evaluate();
  await turn();
  f.release();
  const value = await result;
  t.diagnostic(JSON.stringify(f.trace));
  assert.equal(typeof value === 'boolean' ? value : value.ok, true, JSON.stringify(f.trace));
  assert.equal(value.exported.revision, 3);
  assert.equal(value.imported.revision, 4);
});

test('route content respects the store omission of null snapshot fields', async () => {
  const f = await fixture({nullSnapshotFields: true});
  f.release(); await f.settled();
  const result = await f.evaluate();
  assert.equal(result.ok, true, JSON.stringify(result));
});

for (const [name, options] of [
  ['a failed queued save', {failSave: true}],
  ['an incorrect active session', {wrongActive: true}],
  ['changed imported content', {corruptImport: true}],
  ['lost existing session content', {corruptExisting: true}],
]) test(`route checks reject ${name}`, async () => {
  const f = await fixture(options);
  f.release();
  await f.settled();
  const result = await f.evaluate();
  assert.equal(result.ok, false, JSON.stringify(result));
  assert.doesNotMatch(JSON.stringify(result), /Private original route|Private new route|Private point/);
  assert.equal(f.timers.size, 0);
});

test('HTTP export failure reports its status and error without attempting import', async () => {
  const f = await fixture({exportStatus: 503});
  f.release(); await f.settled();
  const result = await f.evaluate();
  assert.equal(result.ok, false);
  assert.equal(result.exported.status, 503);
  assert.equal(result.exported.error, 'Synthetic export failure');
  assert.equal(f.requests.filter(request => request.method === 'POST').length, 0);
});

test('an independent writer still causes a visible conflict without retry', async () => {
  const f = await fixture({concurrentWriter: true});
  f.release(); await f.settled();
  const result = await f.evaluate();
  assert.equal(result.ok, false);
  assert.equal(result.imported.status, 409);
  assert.match(result.imported.error, /autre fenêtre/);
  assert.equal(f.requests.filter(request => request.method === 'POST').length, 1);
});

test('stalled saves fail within the existing fetch deadline and release the timer', async () => {
  const f = await fixture();
  const result = f.evaluate();
  await turn();
  try {
    assert.equal(f.timers.size, 1);
    const timer = [...f.timers.values()][0];
    assert.equal(timer.delay, 10000);
    timer.callback();
    const value = await result;
    assert.equal(value.ok, false);
    assert.equal(value.phase, 'save');
    assert.match(value.error, /deadline/i);
    assert.equal(f.requests.filter(request => request.method === 'GET').length, 0);
    assert.equal(f.timers.size, 0);
  } finally {f.release(); await f.settled();}
  await turn();
  assert.equal(f.requests.filter(request => request.method === 'GET').length, 0);
});
