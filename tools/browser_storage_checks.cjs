"use strict";
const assert = require('node:assert/strict');
const {randomUUID} = require('node:crypto');

function documentUrl(value) {
  const url = new URL(value);
  url.hash = '';
  return url.href;
}

async function navigationDiagnostic(response, sourceUrl, navigation) {
  const request = response.request();
  const headers = async resource => {
    try {
      const values = await resource.allHeaders();
      return Object.fromEntries(Object.entries(values).map(([key, value]) =>
        [key, /^(cookie|set-cookie|authorization|x-botw-session-token)$/i.test(key) ? '[redacted]' : value]));
    } catch (error) {
      return {unavailable: String(error)};
    }
  };
  const diagnostic = {status: 'storage-document-response', sourceUrl, navigation,
    request: {url: request.url(), method: request.method(), headers: await headers(request)},
    response: {status: response.status(), headers: await headers(response)}};
  if (!response.ok()) {
    try { diagnostic.response.body = await response.text(); }
    catch (error) { diagnostic.response.bodyError = String(error); }
  }
  console.log(JSON.stringify(diagnostic));
  return diagnostic;
}

async function navigateToRenderedApplication(page, url, language, {reload = false} = {}) {
  // Enter from about:blank as a browser navigation, not its opaque origin's
  // script. Document-triggered navigation is reserved for the local origin.
  const sourceUrl = page.url();
  const initial = sourceUrl === 'about:blank';
  assert(!initial || !reload, 'A blank page cannot reload the application');
  assert(initial || new URL(sourceUrl).origin === new URL(url).origin,
    'Document navigation must start on the application origin');
  const navigation = initial ? 'playwright-goto' : reload ? 'document-reload' : 'document-assign';
  const expectedUrl = documentUrl(url);
  const marker = '__botwNavigationProbe_' + randomUUID();
  await page.evaluate(key => { window[key] = true; }, marker);
  let response, diagnostic, rejectResponse;
  const rejectedResponse = new Promise((_, reject) => { rejectResponse = reject; });
  const observeResponse = candidate => {
    const request = candidate.request();
    if (request.isNavigationRequest() && request.frame() === page.mainFrame() &&
        documentUrl(candidate.url()) === expectedUrl) {
      response = candidate;
      diagnostic = navigationDiagnostic(candidate, sourceUrl, navigation);
      if (!candidate.ok()) diagnostic.then(details => {
        const error = new Error('The browser did not receive a successful main document (HTTP ' + candidate.status() + ')');
        error.navigationDiagnostic = details;
        rejectResponse(error);
      }, rejectResponse);
    }
  };
  page.on('response', observeResponse);
  try {
    const command = initial ? page.goto(url, {waitUntil: 'commit'}) : page.evaluate(({url, reload}) => {
      if (reload) window.location.reload();
      else window.location.assign(url);
    }, {url, reload});
    const rendered = (async () => {
      await waitForRenderedApplication(page, language, marker);
      await diagnostic;
      assert(response?.ok(), 'The browser did not receive a successful main document');
      assert.equal(documentUrl(page.url()), expectedUrl, 'The browser rendered the wrong URL');
      assert(await page.evaluate(key => !Object.prototype.hasOwnProperty.call(window, key), marker),
        'The browser kept the previous document instead of navigating');
      return response;
    })();
    // Firefox's command can remain pending after the independent proof succeeds.
    // Conversely, an HTTP rejection must not wait for application readiness.
    return await Promise.race([command.then(() => rendered), rendered, rejectedResponse]);
  } finally {
    page.off('response', observeResponse);
  }
}

async function waitForRenderedApplication(page, language, marker = null) {
  // The report is assigned before preferences are applied to the controls.
  // Wait for the rendered document before reading or changing those controls.
  await page.waitForFunction(({expected, marker}) =>
    (!marker || !Object.prototype.hasOwnProperty.call(window, marker)) &&
    document.documentElement.lang === expected &&
    typeof report !== 'undefined' && report?.elements?.length > 0 &&
    document.querySelector('#refresh')?.disabled === false &&
    document.querySelectorAll('#categories [data-filter-type]').length > 0,
  {expected: language, marker}, {timeout: 30000});
}

async function selectRenderedOption(page, selector, value) {
  // Locator actions also wait for pending navigation before touching controls.
  // Keep their visibility/enabled checks and dispatch the same select events.
  await page.waitForFunction(({selector, value}) => {
    const element = document.querySelector(selector);
    return element?.tagName === 'SELECT' && !element.matches(':disabled') &&
      Array.from(element.getClientRects()).some(rect => rect.width > 0 && rect.height > 0) &&
      getComputedStyle(element).visibility === 'visible' &&
      Array.from(element.options).some(option => option.value === value && !option.matches(':disabled'));
  }, {selector, value}, {timeout: 30000});
  await page.evaluate(({selector, value}) => {
    const element = document.querySelector(selector);
    if (!element || element.matches(':disabled') ||
        !Array.from(element.getClientRects()).some(rect => rect.width > 0 && rect.height > 0) ||
        getComputedStyle(element).visibility !== 'visible' ||
        !Array.from(element.options).some(option => option.value === value && !option.matches(':disabled'))) {
      throw new Error('Unavailable select or option: ' + selector + '=' + value);
    }
    element.focus();
    element.value = value;
    if (element.value !== value) throw new Error('Unavailable option: ' + selector + '=' + value);
    element.dispatchEvent(new Event('input', {bubbles: true, composed: true}));
    element.dispatchEvent(new Event('change', {bubbles: true}));
  }, {selector, value});
}

async function runBrowserStorageChecks(browser, baseUrl,
  onProgress = stage => console.log(JSON.stringify({status: 'progress', stage}))) {
  for (const mode of ['disabled', 'quota-and-corrupt-cache', 'language-write-timeout']) {
    const operation = async (name, action) => {
      const stage = 'storage:' + mode + ':' + name;
      onProgress(stage);
      const started = Date.now();
      try {
        const result = await action();
        console.log(JSON.stringify({status: 'storage-operation-complete', stage, elapsed_ms: Date.now() - started}));
        return result;
      } catch (error) {
        console.error(JSON.stringify({status: 'storage-operation-failed', stage, error: String(error)}));
        throw error;
      }
    };
    const context = await browser.newContext({viewport: {width: 1440, height: 900}});
    try {
      await context.addInitScript(mode => {
        if (mode === 'disabled') {
          Object.defineProperty(window, 'localStorage', {get() { throw new DOMException('Blocked', 'SecurityError'); }});
        } else if (mode === 'quota-and-corrupt-cache') {
          Storage.prototype.getItem = function(key) {
            return key === 'botw-companion-sync-interval' ? 'corrupt value' : null;
          };
          Storage.prototype.setItem = function() { throw new DOMException('Full', 'QuotaExceededError'); };
          Storage.prototype.removeItem = function() { throw new DOMException('Blocked', 'SecurityError'); };
        }
      }, mode);
      const page = await context.newPage();
      assert.equal(page.url(), 'about:blank', mode + ': expected a fresh blank page');
      let interruptedLanguageWrite = false;
      if (mode === 'language-write-timeout') {
        await page.route('**/api/language', async route => {
          if (interruptedLanguageWrite || route.request().method() !== 'PUT') return route.continue();
          interruptedLanguageWrite = true;
          // The client must abandon this ancillary write and finish startup.
          await new Promise(resolve => setTimeout(resolve, 5000));
          await route.abort('failed').catch(() => {});
        });
      }
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      const requests = [];
      page.on('request', request => requests.push({event: 'request', path: new URL(request.url()).pathname}));
      page.on('requestfailed', request => requests.push({event: 'failed', path: new URL(request.url()).pathname,
        error: request.failure()?.errorText}));
      page.on('response', response => requests.push({event: 'response', path: new URL(response.url()).pathname,
        status: response.status()}));
      if (mode === 'quota-and-corrupt-cache') {
        await page.route('**/api/preferences', async route => {
          if (route.request().method() !== 'GET') return route.continue();
          const response = await route.fetch();
          const json = await response.json();
          delete json.values.sync_interval;
          await route.fulfill({response, json});
        });
      }
      console.log(JSON.stringify({status: 'progress', stage: 'storage:' + mode}));
      const health = await operation('health', () => context.request.get(baseUrl + '/?lang=en', {timeout: 5000}));
      assert.equal(health.status(), 200, mode + ': server did not serve the document');
      let response;
      try {
        response = await operation('initial-document', () => navigateToRenderedApplication(page, baseUrl + '/?lang=en', 'en'));
      } catch (error) {
        const state = await page.evaluate(() => ({ready: document.readyState, language: document.documentElement.lang,
          report: typeof report !== 'undefined' && report?.elements?.length})).catch(() => ({unavailable: true}));
        console.error(JSON.stringify({status: 'storage-navigation-failed', mode, url: page.url(), state, errors, requests}));
        throw error;
      }
      assert(response?.ok(), mode + ': initial document failed');
      await operation('initial-ready', () => waitForRenderedApplication(page, 'en'));
      assert.equal(await page.locator('html').getAttribute('lang'), 'en');
      if (mode === 'language-write-timeout') assert(interruptedLanguageWrite, 'The hanging language write was not exercised');
      await operation('dismiss-tutorial', () => page.evaluate(() => {
        const button = document.querySelector('#skipTutorial');
        if (button && Array.from(button.getClientRects()).some(rect => rect.width > 0 && rect.height > 0) &&
            getComputedStyle(button).visibility === 'visible') {
          if (button.matches(':disabled')) throw new Error('The tutorial skip button is disabled');
          button.click();
        }
      }));
      assert(await page.evaluate(() => Number.isFinite(syncInterval) && syncInterval >= 5), mode + ': invalid poll interval');
      await operation('select-sync-interval', () => selectRenderedOption(page, '#syncInterval', '15'));
      await operation('sync-preference-applied', () => page.waitForFunction(() => preferencesData.values.sync_interval === 15));
      await page.unroute('**/api/preferences');
      const frenchUrl = new URL(page.url());
      frenchUrl.searchParams.set('lang', 'fr');
      // The real language handler owns this navigation, including persistence.
      await operation('select-language', () => selectRenderedOption(page, '#languageSelect', 'fr'));
      await operation('language-ready', () => waitForRenderedApplication(page, 'fr'));
      assert.equal(documentUrl(page.url()), documentUrl(frenchUrl), mode + ': language URL did not change');
      const reloaded = await operation('reload-document', () => navigateToRenderedApplication(page, page.url(), 'fr', {reload: true}));
      assert(reloaded?.ok(), mode + ': reloaded document failed');
      await operation('reload-ready', () => waitForRenderedApplication(page, 'fr'));
      assert.equal(await page.locator('#syncInterval').inputValue(), '15', mode + ': server preferences were lost');
      const savedPreferences = await operation('persisted-preferences', () => context.request.get(baseUrl + '/api/preferences'));
      assert(savedPreferences.ok(), mode + ': persisted preferences were unavailable');
      assert.equal((await savedPreferences.json()).values.sync_interval, 15,
        mode + ': persisted sync interval was lost');
      assert.deepEqual(errors, [], mode + ': uncaught browser errors');
    } finally {
      await operation('close-context', () => context.close());
    }
  }
}
module.exports = {runBrowserStorageChecks, navigateToRenderedApplication, selectRenderedOption};
