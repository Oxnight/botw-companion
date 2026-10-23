"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const {EventEmitter} = require("node:events");
const {randomUUID} = require("node:crypto");
const fs = require("node:fs");
const vm = require("node:vm");
const {handleUpdateRequest, assertHandoffBootstrap, trackHandoffErrors,
  assertNoHandoffErrors} = require("../tools/browser_update_checks.cjs");

function fixtureResponse() {
  return {
    statusCode: 200, headers: {},
    setHeader(name, value) { this.headers[name.toLowerCase()] = value; },
    writeHead(status, headers = {}) {
      this.statusCode = status;
      for (const [name, value] of Object.entries(headers)) this.setHeader(name, value);
    },
    end(value) { this.body = Buffer.from(value); }
  };
}

function responseFor(url, cookie = "") {
  const request = Object.assign(new EventEmitter(), {url, headers: {cookie}});
  const response = fixtureResponse();
  handleUpdateRequest(request, response, {token: "old-session", handoff: null});
  return response;
}

function fixtureDocument(locale) {
  const other = locale === "en" ? "fr" : "en";
  const cookie = "botw-language=" + other;
  const response = responseFor("/?lang=" + locale, cookie);
  const scripts = [...response.body.toString().matchAll(/<script(?: src="([^"]+)")?>([\s\S]*?)<\/script>/g)]
    .map(([, src, source]) => ({src, source}));
  const location = new URL("http://127.0.0.1:18765/?lang=" + locale);
  location.replace = () => assert.fail("Explicit document locale must not redirect");
  const document = {cookie, documentElement: {lang: locale, dataset: {}}, addEventListener() {},
    querySelector: () => ({content: "old-session"})};
  const context = vm.createContext({URL, URLSearchParams, AbortController, document, location,
    crypto: {randomUUID}, history: {state: null, replaceState(state) { this.state = state; }},
    localStorage: {getItem: () => other, setItem() {}},
    addEventListener() {}, setTimeout() {}, clearTimeout() {},
    fetch: async path => ({ok: true, json: async () => JSON.parse(responseFor(path).body)})});
  context.window = context;
  return {context, scripts, cookie};
}

function fixturePage(context) {
  return {url: () => context.location.href, evaluate: async operation =>
    JSON.parse(JSON.stringify(vm.runInContext("(" + operation.toString() + ")()", context)))};
}

for (const locale of ["fr", "en"]) {
  test(`${locale}: actual handoff document initializes localization before language and session scripts`, async () => {
    const {context, scripts, cookie} = fixtureDocument(locale);
    for (const {src, source} of scripts) {
      vm.runInContext(src ? responseFor(src, cookie).body.toString() : source, context,
        {filename: src || "handoff-inline.js"});
    }
    assert.equal(context.BOTWI18n.failed, false);
    assert.equal(context.BOTWI18n.locale, locale);
    assert.equal(typeof context.BOTWI18n.t("inactive-tab-title"), "string");
    assert.equal(typeof context.BOTWBrowserSession.init, "function");
    await assertHandoffBootstrap(fixturePage(context), locale);
    const production = fs.readFileSync(`botw_companion/locales/${locale}/index.html`, "utf8");
    const required = [`/locale.js?lang=${locale}`, "/i18n.js", "/language.js", "/browser_session.js"];
    const productionOrder = [...production.matchAll(/<script src="([^"]+)">/g)]
      .map(([, src]) => src).filter(src => required.includes(src));
    assert.deepEqual(scripts.filter(script => script.src).map(script => script.src), required);
    assert.deepEqual(productionOrder, required);
  });

  test(`${locale}: fixture serves the exact generated catalog despite an opposing cookie`, () => {
    const response = responseFor(`/locale.js?lang=${locale}`, "botw-language=" + (locale === "en" ? "fr" : "en"));
    assert.equal(response.statusCode, 200);
    assert.equal(response.headers["content-type"], "text/javascript; charset=utf-8");
    assert.deepEqual(response.body, fs.readFileSync(`botw_companion/locales/${locale}/browser.js`));
  });
}

test("fixture serves the actual shared runtime and rejects missing or unsafe locale selection", () => {
  const runtime = responseFor("/i18n.js");
  assert.equal(runtime.headers["content-type"], "text/javascript; charset=utf-8");
  assert.deepEqual(runtime.body, fs.readFileSync("botw_companion/web/i18n.js"));
  for (const path of ["/locale.js", "/locale.js?lang=invalid", "/locale.js?lang=..%2Fen"]) {
    assert.equal(responseFor(path, "botw-language=en").statusCode, 404);
  }
});

for (const missing of ["catalog", "runtime"]) {
  test(`missing ${missing} fails the bootstrap assertion before waiting for handoff`, async () => {
    const {context} = fixtureDocument("en");
    if (missing !== "catalog") vm.runInContext(responseFor("/locale.js?lang=en").body.toString(), context);
    if (missing !== "runtime") vm.runInContext(responseFor("/i18n.js").body.toString(), context);
    await assert.rejects(assertHandoffBootstrap(fixturePage(context), "en"),
      /Handoff fixture BOTWI18n bootstrap failed.*locale\.js\?lang=en.*i18n\.js/);
  });
}

test("JavaScript errors from every tab are retained and fail the handoff fixture", () => {
  const context = new EventEmitter();
  const errors = trackHandoffErrors(context);
  assertNoHandoffErrors(errors);
  for (const tab of ["selected", "duplicate", "popup", "reopened", "late", "closed"]) {
    context.emit("weberror", {page: () => ({url: () => "http://fixture/" + tab}),
      error: () => new Error("Synthetic " + tab + " failure")});
  }
  context.emit("weberror", {page: () => null, error: () => new Error("Synthetic detached page failure")});
  assert.equal(errors.length, 7);
  assert.equal(errors[2].url, "http://fixture/popup");
  assert.equal(errors[3].message, "Synthetic reopened failure");
  assert.equal(errors[6].url, "unknown page");
  assert.throws(() => assertNoHandoffErrors(errors), /Synthetic popup failure.*Synthetic reopened failure/);
});

test("claim authentication still uses current identity when the request body completes", () => {
  const request = Object.assign(new EventEmitter(), {url: "/api/browser/claim",
    headers: {"x-botw-session-token": "old-session"}});
  const response = fixtureResponse();
  const state = {token: "old-session", handoff: {id: "old-update", client_id: null, claimed_by: null}};
  handleUpdateRequest(request, response, state);
  request.emit("data", JSON.stringify({id: "old-update", client_id: "old-client"}));
  state.token = "new-session";
  state.handoff = {id: "new-update", client_id: null, claimed_by: null};
  request.emit("end");
  assert.equal(response.statusCode, 403);
  assert.equal(state.handoff.claimed_by, null);
});
