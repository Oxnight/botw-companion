"use strict";
const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const {test} = require('node:test');
const {runInNewContext} = require('node:vm');
const {navigateToRenderedApplication, selectRenderedOption, runBrowserStorageChecks} = require('../tools/browser_storage_checks.cjs');

const target = 'http://127.0.0.1:18765/?lang=en';
const timeout = () => Object.assign(new Error('Navigation lifecycle timed out'), {name: 'TimeoutError'});

class NavigationPage extends EventEmitter {
  constructor(options = {}) {
    super();
    this.options = options;
    this.frame = {};
    this.document = {};
    this.location = 'about:blank';
    this.readinessChecks = 0;
    this.operations = [];
  }
  mainFrame() { return this.frame; }
  url() { return this.location; }
  async evaluate(operation, marker) {
    this.document.location = {
      assign: url => this.perform('assign', url),
      reload: () => this.perform('reload', this.location),
    };
    return runInNewContext('(' + operation.toString() + ')(marker)', {
      window: this.document, marker, ...this.globals(), Event,
      getComputedStyle: element => ({visibility: element.hidden ? 'hidden' : 'visible'}),
    });
  }
  globals() {
    return {
      document: {documentElement: {lang: this.httpRejected ? '' : this.options.wrongLanguage ? 'fr' : new URL(this.location).searchParams.get('lang')},
        querySelector: selector => selector === '#refresh' ? {disabled: false} : this.controls?.[selector],
        querySelectorAll: () => [{}]},
      report: {elements: this.options.notReady ? [] : [{}]},
      preferencesData: {values: this.preferences || {}},
      syncInterval: 15,
    };
  }
  async waitForFunction(operation, argument, options) {
    this.readinessChecks += 1;
    if (options) assert.equal(options.timeout, 30000);
    if (this.httpRejected) return new Promise(() => {});
    if (!await this.evaluate(operation, argument)) throw timeout();
  }
  perform(kind, url) {
    const blankScript = this.location === 'about:blank' && kind === 'assign';
    this.operations.push(kind);
    if (!this.options.staleDocument) this.document = {};
    const expected = new URL(url); expected.hash = '';
    this.location = this.options.wrongUrl ? target.replace('lang=en', 'lang=fr') : expected.href + '#browser-client=example';
    const status = this.options.responseStatus || (blankScript ? 403 : this.options.badHttp ? 500 : 200);
    this.httpRejected = status >= 400;
    const headers = this.options.requestHeaders || {host: '127.0.0.1:18765',
      'sec-fetch-site': blankScript ? 'cross-site' : kind === 'goto' ? 'none' : 'same-origin',
      ...(blankScript ? {origin: 'null'} : {})};
    const response = {
      ok: () => status === 200,
      status: () => status,
      url: () => expected.href,
      allHeaders: async () => ({'content-type': 'application/json; charset=utf-8'}),
      text: async () => this.options.responseBody || '{"erreur":"Origine non autorisée"}',
      request: () => ({isNavigationRequest: () => !this.options.apiResponse,
        frame: () => this.options.iframe ? {} : this.frame,
        url: () => expected.href, method: () => 'GET', allHeaders: async () => headers}),
    };
    this.lastResponse = response;
    if (!this.options.noResponse) this.emit('response', response);
    this.options.onDocument?.(this);
    if (this.options.error) throw this.options.error;
    return response;
  }
  async goto(url, options) {
    assert.deepEqual(options, {waitUntil: 'commit'});
    const response = this.perform('goto', url);
    // Model Firefox's pending command even though the document is available.
    return this.options.pendingNavigation ? new Promise(() => {}) : response;
  }
  async reload() { throw new Error('Still waiting for Firefox navigation'); }
}

test('ordinary navigation still requires the successful document and rendered controls', async () => {
  const page = new NavigationPage();
  assert((await navigateToRenderedApplication(page, target, 'en')).ok());
  assert.equal(page.readinessChecks, 1);
  assert.deepEqual(page.operations, ['goto']);
  assert.equal(page.listenerCount('response'), 0);
});

test('a rendered document does not wait for the pending navigation lifecycle', async () => {
  const page = new NavigationPage({pendingNavigation: true});
  assert((await navigateToRenderedApplication(page, target, 'en')).ok());
  assert.equal(page.readinessChecks, 1);
  assert.equal(page.listenerCount('response'), 0);
});

test('the blank-origin model rejects script entry while the helper uses browser entry', async () => {
  const scriptPage = new NavigationPage();
  await scriptPage.evaluate(url => window.location.assign(url), target);
  assert.equal(scriptPage.lastResponse.status(), 403);
  const page = new NavigationPage();
  assert((await navigateToRenderedApplication(page, target, 'en')).ok());
  assert.deepEqual(page.operations, ['goto']);
});

test('a document already on the local origin uses its own navigation', async () => {
  const page = new NavigationPage();
  page.location = target;
  await navigateToRenderedApplication(page, target, 'en');
  assert.deepEqual(page.operations, ['assign']);
});

test('HTTP 403 reports headers and body without waiting for application readiness', {timeout: 1000}, async () => {
  const page = new NavigationPage({responseStatus: 403, pendingNavigation: true,
    requestHeaders: {origin: 'null', 'sec-fetch-site': 'cross-site', cookie: 'synthetic-secret'},
    responseBody: '{"erreur":"Origine non autorisée"}'});
  await assert.rejects(navigateToRenderedApplication(page, target, 'en'), error => {
    assert.match(error.message, /HTTP 403/);
    const details = error.navigationDiagnostic;
    assert.equal(details.sourceUrl, 'about:blank');
    assert.equal(details.navigation, 'playwright-goto');
    assert.equal(details.request.headers.origin, 'null');
    assert.equal(details.request.headers['sec-fetch-site'], 'cross-site');
    assert.equal(details.request.headers.cookie, '[redacted]');
    assert.equal(details.response.body, '{"erreur":"Origine non autorisée"}');
    return true;
  });
  assert.equal(page.listenerCount('response'), 0);
});

test('a document on another origin cannot use local document navigation', async () => {
  const page = new NavigationPage();
  page.location = 'https://unrelated.example/';
  await assert.rejects(navigateToRenderedApplication(page, target, 'en'), /application origin/);
  assert.deepEqual(page.operations, []);
});

test('reload uses the same document, HTTP and readiness verification', async () => {
  const page = new NavigationPage();
  page.location = target;
  await navigateToRenderedApplication(page, target, 'en', {reload: true});
  assert.deepEqual(page.operations, ['reload']);
  assert.equal(page.readinessChecks, 1);
});

for (const [name, options] of Object.entries({
  'missing browser response': {noResponse: true},
  'failed HTTP response': {badHttp: true},
  'an API response instead of the document': {apiResponse: true},
  'an iframe response instead of the main document': {iframe: true},
  'the old document still displayed': {staleDocument: true},
  'the wrong language URL': {wrongUrl: true},
  'the wrong document language': {wrongLanguage: true},
  'unrendered application controls': {notReady: true},
})) {
  test('navigation must still fail with ' + name, async () => {
    const page = new NavigationPage(options);
    await assert.rejects(navigateToRenderedApplication(page, target, 'en'));
    assert.equal(page.listenerCount('response'), 0);
  });
}

test('non-timeout navigation errors cannot be accepted even with a rendered document', async () => {
  const error = new Error('NS_BINDING_ABORTED');
  const page = new NavigationPage({error});
  await assert.rejects(navigateToRenderedApplication(page, target, 'en'), actual => actual === error);
  assert.equal(page.listenerCount('response'), 0);
});

function storagePage(options = {}) {
  const page = new NavigationPage(options);
  page.preferences = {};
  const events = [];
  function select(selector, values, changed) {
    return {tagName: 'SELECT', value: values[0],
      options: values.map(value => ({value, matches: () => false})),
      matches() { return Boolean(this.disabled); }, getClientRects() { return this.hidden ? [] : [{width: 100, height: 24}]; },
      focus() { events.push({selector, event: 'focus'}); },
      dispatchEvent(event) {
        events.push({selector, event: event.type, bubbles: event.bubbles, composed: event.composed});
        if (event.type === 'change') changed(this.value);
      }};
  }
  page.controls = {
    '#syncInterval': select('#syncInterval', ['5', '15'], value => { page.preferences.sync_interval = Number(value); }),
    '#languageSelect': select('#languageSelect', ['en', 'fr'], value => {
      const url = new URL(page.url()); url.searchParams.set('lang', value);
      page.perform('assign', url.href);
    }),
    '#skipTutorial': {hidden: false, matches: () => false, getClientRects: () => [{width: 100, height: 24}],
      click() { this.hidden = true; events.push({event: 'skip'}); }},
  };
  const onDocument = options.onDocument;
  options.onDocument = () => {
    page.controls['#syncInterval'].value = options.lostPreferences && page.operations.at(-1) === 'reload'
      ? '5' : String(page.preferences.sync_interval || 5);
    onDocument?.(page);
  };
  page.locator = selector => ({
    getAttribute: async () => new URL(page.url()).searchParams.get('lang'),
    inputValue: async () => page.controls[selector].value,
    selectOption: async () => { throw new Error('Still waiting for Firefox navigation before selectOption'); },
    click: async () => { throw new Error('Still waiting for Firefox navigation before click'); },
    evaluate: async () => { throw new Error('Still waiting for Firefox navigation before resolving a locator'); },
  });
  page.unroute = async () => {};
  return {page, events};
}

test('selecting a ready control keeps real input/change handlers without navigation prechecks', async () => {
  const {page, events} = storagePage();
  await selectRenderedOption(page, '#syncInterval', '15');
  assert.equal(page.preferences.sync_interval, 15);
  assert.deepEqual(events, [{selector: '#syncInterval', event: 'focus'},
    {selector: '#syncInterval', event: 'input', bubbles: true, composed: true},
    {selector: '#syncInterval', event: 'change', bubbles: true, composed: false}]);
});

for (const unavailable of ['missing', 'hidden', 'disabled', 'missing-option', 'disabled-option']) {
  test('selecting an unavailable control still fails: ' + unavailable, async () => {
    const {page, events} = storagePage();
    const element = page.controls['#syncInterval'];
    if (unavailable === 'missing') delete page.controls['#syncInterval'];
    if (unavailable === 'hidden') element.hidden = true;
    if (unavailable === 'disabled') element.disabled = true;
    if (unavailable === 'missing-option') element.options = [];
    if (unavailable === 'disabled-option') element.options.forEach(option => { option.matches = () => true; });
    await assert.rejects(selectRenderedOption(page, '#syncInterval', '15'), {name: 'TimeoutError'});
    assert.deepEqual(events, []);
  });
}

async function firstStorageScenario(options = {}) {
  const {page, events} = storagePage(options), stages = [];
  let contexts = 0, closed = false;
  const finished = new Error('First scenario completed');
  const context = {
    addInitScript: async () => {}, newPage: async () => page,
    request: {get: async url => ({status: () => 200, ok: () => true,
      json: async () => ({values: {...page.preferences}})})},
    close: async () => { closed = true; },
  };
  const browser = {newContext: async () => {
    if (++contexts > 1) throw finished;
    return context;
  }};
  const run = runBrowserStorageChecks(browser, 'http://127.0.0.1:18765', stage => stages.push(stage));
  await assert.rejects(run, error => options.failure ? options.failure(error) : error === finished);
  assert(closed);
  return {page, events, stages};
}

test('the disabled-storage scenario completes preferences, language and reload with navigation still pending', async () => {
  const {page, events, stages} = await firstStorageScenario();
  assert.equal(page.preferences.sync_interval, 15);
  assert.equal(new URL(page.url()).searchParams.get('lang'), 'fr');
  assert.deepEqual(page.operations, ['goto', 'assign', 'reload']);
  assert(events.some(event => event.event === 'skip'));
  for (const operation of ['initial-document', 'select-sync-interval', 'sync-preference-applied',
    'select-language', 'language-ready', 'reload-document', 'persisted-preferences', 'close-context']) {
    assert(stages.includes('storage:disabled:' + operation), operation);
  }
});

test('uncaught JavaScript errors still fail the storage scenario after a rendered document', async () => {
  await firstStorageScenario({onDocument: page => page.emit('pageerror', new Error('Synthetic script failure')),
    failure: error => /uncaught browser errors/.test(error.message)});
});

test('losing the persisted preference on reload still fails the storage scenario', async () => {
  await firstStorageScenario({lostPreferences: true,
    failure: error => /server preferences were lost/.test(error.message)});
});

test('an HTTP error remains a failure when navigation itself succeeds', async () => {
  const page = new NavigationPage({badHttp: true});
  await assert.rejects(navigateToRenderedApplication(page, target, 'en'), /successful main document/);
  assert.equal(page.listenerCount('response'), 0);
});
