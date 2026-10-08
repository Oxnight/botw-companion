"use strict";
const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const {test} = require('node:test');
const {runInNewContext} = require('node:vm');
const {navigateToRenderedApplication} = require('../tools/browser_storage_checks.cjs');

const target = 'http://127.0.0.1:18765/?lang=en';
const timeout = () => Object.assign(new Error('Navigation lifecycle timed out'), {name: 'TimeoutError'});

class NavigationPage extends EventEmitter {
  constructor(options = {}) {
    super();
    this.options = options;
    this.frame = {};
    this.document = {};
    this.location = target;
    this.readinessChecks = 0;
    this.operations = [];
  }
  mainFrame() { return this.frame; }
  url() { return this.location; }
  async evaluate(operation, marker) {
    return runInNewContext('(' + operation.toString() + ')(marker)', {window: this.document, marker});
  }
  async waitForFunction(operation, language, options) {
    this.readinessChecks += 1;
    assert.equal(language, 'en');
    assert.equal(options.timeout, 30000);
    if (this.options.notReady) throw timeout();
  }
  async perform(kind, options) {
    this.operations.push(kind);
    assert.equal(options.waitUntil, 'commit');
    if (!this.options.staleDocument) this.document = {};
    this.location = this.options.wrongUrl ? target.replace('lang=en', 'lang=fr') : target + '#browser-client=example';
    const response = {
      ok: () => !this.options.badHttp,
      url: () => target,
      request: () => ({isNavigationRequest: () => !this.options.apiResponse,
        frame: () => this.options.iframe ? {} : this.frame}),
    };
    if (!this.options.noResponse) this.emit('response', response);
    if (this.options.error) throw this.options.error;
    return response;
  }
  async goto(url, options) {
    assert.equal(url, target);
    return this.perform('goto', options);
  }
  async reload(options) { return this.perform('reload', options); }
}

test('ordinary navigation still requires the successful document and rendered controls', async () => {
  const page = new NavigationPage();
  assert((await navigateToRenderedApplication(page, target, 'en')).ok());
  assert.equal(page.readinessChecks, 1);
  assert.equal(page.listenerCount('response'), 0);
});

test('a lifecycle timeout is recoverable only after a successful new rendered document', async () => {
  const page = new NavigationPage({error: timeout()});
  assert((await navigateToRenderedApplication(page, target, 'en')).ok());
  assert.equal(page.readinessChecks, 1);
  assert.equal(page.listenerCount('response'), 0);
});

test('reload uses the same document, HTTP and readiness verification', async () => {
  const page = new NavigationPage({error: timeout()});
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
  'unrendered application controls': {notReady: true},
})) {
  test('a timeout must still fail with ' + name, async () => {
    const page = new NavigationPage({...options, error: timeout()});
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

test('an HTTP error remains a failure when navigation itself succeeds', async () => {
  const page = new NavigationPage({badHttp: true});
  await assert.rejects(navigateToRenderedApplication(page, target, 'en'), /successful main document/);
  assert.equal(page.listenerCount('response'), 0);
});
