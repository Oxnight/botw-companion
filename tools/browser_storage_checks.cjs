"use strict";
const assert = require('node:assert/strict');
const {randomUUID} = require('node:crypto');

function documentUrl(value) {
  const url = new URL(value);
  url.hash = '';
  return url.href;
}

async function navigateToRenderedApplication(page, url, language, {reload = false} = {}) {
  // Firefox can time out its navigation lifecycle after the document has
  // actually loaded. A timeout is recoverable only with independent evidence
  // of a successful main-frame response and a new, correctly rendered document.
  const expectedUrl = documentUrl(url);
  const marker = '__botwNavigationProbe_' + randomUUID();
  await page.evaluate(key => { window[key] = true; }, marker);
  let response;
  const observeResponse = candidate => {
    const request = candidate.request();
    if (request.isNavigationRequest() && request.frame() === page.mainFrame() &&
        documentUrl(candidate.url()) === expectedUrl) response = candidate;
  };
  page.on('response', observeResponse);
  try {
    let lifecycleTimeout = false;
    try {
      if (reload) await page.reload({waitUntil: 'commit'});
      else await page.goto(url, {waitUntil: 'commit'});
    } catch (error) {
      if (error?.name !== 'TimeoutError' || !response?.ok()) throw error;
      lifecycleTimeout = true;
    }
    assert(response?.ok(), 'The browser did not receive a successful main document');
    await waitForRenderedApplication(page, language);
    assert.equal(documentUrl(page.url()), expectedUrl, 'The browser rendered the wrong URL');
    assert(await page.evaluate(key => !Object.prototype.hasOwnProperty.call(window, key), marker),
      'The browser kept the previous document instead of navigating');
    if (lifecycleTimeout) console.warn(JSON.stringify({status: 'navigation-lifecycle-timeout',
      url: page.url(), verified: 'main-document-http-and-rendered-application'}));
    return response;
  } finally {
    page.off('response', observeResponse);
  }
}

async function waitForRenderedApplication(page, language) {
  // The report is assigned before preferences are applied to the controls.
  // Wait for the rendered document before reading or changing those controls.
  await page.waitForFunction(expected =>
    document.documentElement.lang === expected &&
    typeof report !== 'undefined' && report?.elements?.length > 0 &&
    document.querySelector('#refresh')?.disabled === false &&
    document.querySelectorAll('#categories [data-filter-type]').length > 0,
  language, {timeout: 30000});
}

async function runBrowserStorageChecks(browser, baseUrl) {
  for (const mode of ['disabled', 'quota-and-corrupt-cache', 'language-write-timeout']) {
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
      const health = await context.request.get(baseUrl + '/?lang=en', {timeout: 5000});
      assert.equal(health.status(), 200, mode + ': server did not serve the document');
      let response;
      try {
        response = await navigateToRenderedApplication(page, baseUrl + '/?lang=en', 'en');
      } catch (error) {
        const state = await page.evaluate(() => ({ready: document.readyState, language: document.documentElement.lang,
          report: typeof report !== 'undefined' && report?.elements?.length})).catch(() => ({unavailable: true}));
        console.error(JSON.stringify({status: 'storage-navigation-failed', mode, url: page.url(), state, errors, requests}));
        throw error;
      }
      assert(response?.ok(), mode + ': initial document failed');
      await waitForRenderedApplication(page, 'en');
      assert.equal(await page.locator('html').getAttribute('lang'), 'en');
      if (mode === 'language-write-timeout') assert(interruptedLanguageWrite, 'The hanging language write was not exercised');
      if (await page.locator('#skipTutorial').isVisible()) await page.locator('#skipTutorial').click();
      assert(await page.evaluate(() => Number.isFinite(syncInterval) && syncInterval >= 5), mode + ': invalid poll interval');
      await page.locator('#syncInterval').selectOption('15');
      await page.waitForFunction(() => preferencesData.values.sync_interval === 15);
      await page.unroute('**/api/preferences');
      await page.locator('#languageSelect').selectOption('fr');
      await waitForRenderedApplication(page, 'fr');
      const reloaded = await navigateToRenderedApplication(page, page.url(), 'fr', {reload: true});
      assert(reloaded?.ok(), mode + ': reloaded document failed');
      await waitForRenderedApplication(page, 'fr');
      assert.equal(await page.locator('#syncInterval').inputValue(), '15', mode + ': server preferences were lost');
      const savedPreferences = await context.request.get(baseUrl + '/api/preferences');
      assert(savedPreferences.ok(), mode + ': persisted preferences were unavailable');
      assert.equal((await savedPreferences.json()).values.sync_interval, 15,
        mode + ': persisted sync interval was lost');
      assert.deepEqual(errors, [], mode + ': uncaught browser errors');
    } finally {
      await context.close();
    }
  }
}
module.exports = {runBrowserStorageChecks, navigateToRenderedApplication};
