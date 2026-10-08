"use strict";
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");

async function runBrowserUpdateChecks(browser) {
  const root = path.resolve(__dirname, "../botw_companion/web");
  let token = "old-session", handoff = null;
  const bootstrap = fs.readFileSync(path.join(root, "app.js"), "utf8").split("window.fetch =")[0];
  const requests = [];
  const server = http.createServer((request, response) => {
    const url = new URL(request.url, "http://127.0.0.1");
    requests.push({path: url.pathname, token});
    response.setHeader("Cache-Control", "no-store");
    if (url.pathname === "/api/version") {
      response.setHeader("Content-Type", "application/json");
      response.end(JSON.stringify({application: "BOTW Companion", session_token: token, browser_handoff: handoff}));
    } else if (url.pathname === "/api/browser/claim") {
      let body = "";
      request.on("data", chunk => { body += chunk; });
      request.on("end", () => {
        const data = JSON.parse(body);
        if (request.headers["x-botw-session-token"] !== token) {
          response.writeHead(403); response.end("{}"); return;
        }
        if (handoff && data.id === handoff.id && !handoff.claimed_by &&
            [null, data.client_id].includes(handoff.client_id)) handoff.claimed_by = data.client_id;
        response.setHeader("Content-Type", "application/json");
        response.end(JSON.stringify({browser_handoff: handoff}));
      });
    } else if (["/language.js", "/browser_session.js", "/style.css", "/metrics.css", "/armor.css"].includes(url.pathname)) {
      response.setHeader("Content-Type", url.pathname.endsWith(".js") ? "text/javascript" : "text/css");
      response.end(fs.readFileSync(path.join(root, url.pathname.slice(1))));
    } else if (url.pathname === "/unrelated") {
      response.end("<!doctype html><title>Unrelated page</title><h1>Keep this page</h1>");
    } else {
      const lang = url.searchParams.get("lang") === "en" ? "en" : "fr";
      response.setHeader("Content-Type", "text/html; charset=utf-8");
      response.end(`<!doctype html><html lang="${lang}"><head><title>BOTW Companion</title><meta name="botw-session-token" content="${token}"><script src="/language.js"></script>
        <link rel="stylesheet" href="/style.css"><link rel="stylesheet" href="/metrics.css"><link rel="stylesheet" href="/armor.css">
        </head><body><select id="languageSelect"><option value="fr">Français</option><option value="en">English</option></select><main class="detailSection"><div class="guideTitle">
        <h3>${lang === "en" ? "Objective guide" : "Fiche d’accompagnement personnalisée"}</h3>
        <span>${lang === "en" ? "Obstacle or individual lock confirmed" : "Conseils propres à cette famille cartographique"}</span>
        </div><output id="version">${token}</output></main><script src="/browser_session.js"></script>
        <script>${bootstrap}</script><script>window.BOTWBrowserSession.init(${url.pathname === "/late" ? '"old-session"' : 'sessionToken'},()=>{window.stopped=true;});</script></body></html>`);
    }
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const url = `http://127.0.0.1:${server.address().port}`;
  const context = await browser.newContext({viewport: {width: 1200, height: 900}});
  try {
    const selected = await context.newPage();
    selected.on('pageerror', error => console.error('Handoff page error:', error.message));
    await selected.goto(url + "/?lang=en");
    const duplicate = await context.newPage();
    await duplicate.goto(url + "/?lang=fr");
    // Exercise the documented policy fallback even on engines that happen
    // to allow closing a manually created one-entry test page.
    await duplicate.evaluate(() => { window.close = () => {}; });
    const unrelated = await context.newPage();
    await unrelated.goto(url + "/unrelated");
    const popupPromise = context.waitForEvent("page");
    await selected.evaluate(url => window.open(url + "/?lang=fr"), url);
    const popup = await popupPromise;
    await popup.waitForLoadState();
    await popup.waitForFunction(() => !!window.BOTWBrowserSession);
    const clientId = await selected.evaluate(() => window.BOTWBrowserSession.clientId);
    const prepared = {id: "verified-update-handoff", client_id: clientId};
    await selected.evaluate(state => window.BOTWBrowserSession.installed(state), prepared);
    handoff = {...prepared, claimed_by: null}; token = "updated-session";
    await selected.waitForFunction(() => document.getElementById("version")?.textContent === "updated-session");
    assert.equal(handoff.claimed_by, clientId);
    assert.equal(new URL(selected.url()).searchParams.get("lang"), "en");
    for (const page of [duplicate, popup]) {
      if (!page.isClosed()) {
        await page.waitForFunction(() => !!document.querySelector(".shutdownPage")).catch(error => {
          if (!page.isClosed()) throw error;
        });
        if (!page.isClosed()) assert.equal(await page.locator("#version").count(), 0);
      }
    }
    assert.equal(await duplicate.locator('h1').textContent(), 'Cet onglet BOTW Companion n’est plus actif');
    assert.equal(await unrelated.locator("h1").textContent(), "Keep this page");
    // Use the production bootstrap (including fragment cleanup) and the
    // real language selector after the acknowledged update, not before it.
    for (const lang of ["fr", "en", "fr"]) {
      await selected.locator("#languageSelect").selectOption(lang);
      await selected.waitForFunction(language => document.documentElement.lang === language &&
        !!window.BOTWBrowserSession, lang);
      assert.equal(await selected.evaluate(() => window.BOTWBrowserSession.clientId), clientId);
      assert.equal(await selected.locator("#version").textContent(), "updated-session");
      await selected.waitForTimeout(100);
      assert(!selected.isClosed() && !await selected.evaluate(() => !!window.stopped),
        "Language change retired the current application tab");
    }
    for (const [direction, language] of [["goBack", "en"], ["goForward", "fr"]]) {
      await selected[direction]();
      await selected.waitForFunction(lang => document.documentElement.lang === lang &&
        !!window.BOTWBrowserSession, language);
      assert.equal(await selected.evaluate(() => window.BOTWBrowserSession.clientId), clientId);
      await selected.waitForTimeout(100);
      assert.equal(await selected.evaluate(() => !!window.stopped), false,
        "History navigation retired the current tab");
    }
    await selected.evaluate(() => {
      const channel = new BroadcastChannel("botw-companion-update");
      channel.postMessage({type: "handoff", session_token: "old-session",
        handoff: {id: "delayed-old-update", client_id: "unrelated-browser-client-9876"}});
      channel.postMessage({type: "claimed", client_id: "unrelated-browser-client-9876"});
      channel.close();
    });
    await selected.waitForTimeout(150);
    assert.equal(await selected.evaluate(() => !!window.stopped), false,
      "A delayed announcement retired the updated document");
    await selected.reload();
    assert.equal(await selected.evaluate(() => window.BOTWBrowserSession.clientId), clientId);
    // An old launch fragment cannot override the current server's token.
    const staleUrl = await context.newPage();
    await staleUrl.addInitScript(() => { window.close = () => { window.closeAttempts = (window.closeAttempts || 0) + 1; }; });
    await staleUrl.goto(url + "/?lang=en#session=old-session");
    await staleUrl.waitForTimeout(150);
    assert.equal(await staleUrl.evaluate(() => sessionToken), "updated-session");
    assert.equal(await staleUrl.evaluate(() => !!window.stopped || !!window.closeAttempts), false);
    assert.equal(new URL(staleUrl.url()).hash, "");
    await staleUrl.close();
    // A second consecutive update must still reuse the same tab identity.
    const secondPrepared = {id: "second-verified-update-handoff", client_id: clientId};
    await selected.evaluate(state => window.BOTWBrowserSession.installed(state), secondPrepared);
    handoff = {...secondPrepared, claimed_by: null}; token = "second-updated-session";
    await selected.waitForFunction(() => document.getElementById("version")?.textContent === "second-updated-session");
    assert.equal(handoff.claimed_by, clientId);
    await selected.locator("#languageSelect").selectOption("en");
    await selected.waitForFunction(() => document.documentElement.lang === "en" && !!window.BOTWBrowserSession);
    assert.equal(await selected.evaluate(() => window.BOTWBrowserSession.clientId), clientId);
    await selected.waitForTimeout(100);
    assert.equal(await selected.evaluate(() => !!window.stopped), false);
    // The originally selected tab has disappeared: the launcher's fallback
    // releases its reservation, and exactly one new tab can claim it.
    await selected.close();
    // A Dock reopen gets a fresh client while the old claim still exists.
    const reopened = await context.newPage();
    await reopened.addInitScript(() => { window.close = () => { window.closeAttempts = (window.closeAttempts || 0) + 1; }; });
    await reopened.goto(url + "/?lang=en");
    await reopened.waitForTimeout(150);
    assert.equal(await reopened.evaluate(() => !!window.stopped || !!window.closeAttempts), false);
    assert.equal(await reopened.locator("#version").textContent(), "second-updated-session");
    assert.notEqual(await reopened.evaluate(() => window.BOTWBrowserSession.clientId), clientId);
    await reopened.close();
    handoff = {id: "fallback-update-handoff", client_id: null, claimed_by: null};
    const fallback = await context.newPage();
    await fallback.goto(url + "/?lang=fr");
    await fallback.waitForFunction(() => window.BOTWBrowserSession && !window.stopped);
    await new Promise((resolve, reject) => {
      const deadline = Date.now() + 5000;
      function check() {
        if (handoff.claimed_by) resolve();
        else if (Date.now() > deadline) reject(Error("Fallback tab was not acknowledged"));
        else setTimeout(check, 20);
      }
      check();
    });
    const late = await context.newPage();
    await late.addInitScript(() => { window.close = () => {}; });
    await late.goto(url + "/late?lang=en").catch(() => {});
    if (!late.isClosed()) await late.waitForFunction(() => !!document.querySelector(".shutdownPage")).catch(error => {
      if (!late.isClosed()) throw error;
    });
    assert.equal(await late.locator('h1').textContent(), 'This BOTW Companion tab is inactive');
    // Long installs may outlive the bounded persisted handoff. The old tab
    // must retire when a new server appears instead of displaying stale UI.
    handoff = null;
    const expired = await context.newPage();
    await expired.addInitScript(() => { window.close = () => {}; });
    await expired.goto(url + '/?lang=en');
    const expiredId = await expired.evaluate(() => window.BOTWBrowserSession.clientId);
    await expired.evaluate(client => window.BOTWBrowserSession.installed({id: 'expired-handoff', client_id: client}), expiredId);
    token = 'new-session-after-expiry';
    await expired.waitForFunction(() => !!document.querySelector('.shutdownPage'));
    // A normal server restart has no update record. A still-open old page
    // must retire instead of retaining stale code and an invalid API token.
    handoff = null;
    const ordinaryRestart = await context.newPage();
    await ordinaryRestart.addInitScript(() => { window.close = () => {}; });
    await ordinaryRestart.goto(url + '/?lang=en');
    await ordinaryRestart.waitForTimeout(100);
    token = 'ordinary-restart-session';
    await unrelated.evaluate(() => {
      const channel = new BroadcastChannel('botw-companion-update');
      channel.postMessage({type: 'claimed', client_id: 'new-server-browser-client-1234'});
      channel.close();
    });
    await ordinaryRestart.waitForFunction(() => !!document.querySelector('.shutdownPage'));
    assert.equal(await ordinaryRestart.locator('#version').count(), 0);
    // Use actual production CSS, in its real cascade order. Include a long
    // title and several badge lengths rather than checking a CSS declaration.
    handoff = null;
    for (const lang of ["fr", "en"]) {
      const page = await context.newPage();
      await page.goto(url + "/?lang=" + lang);
      for (const width of [760, 1200]) {
        await page.setViewportSize({width, height: 900});
        await page.locator("main").evaluate(node => { node.style.width = "min(380px, 90vw)"; });
        for (const label of ["Verified", "Obstacle or individual lock confirmed", "Conseils propres à cette famille cartographique"]) {
          await page.locator(".guideTitle span").evaluate((node, text) => { node.textContent = text; }, label);
          const centers = await page.locator(".guideTitle").evaluate(node => {
            const a = node.querySelector("h3").getBoundingClientRect(), b = node.querySelector("span").getBoundingClientRect();
            return {difference: Math.abs((a.top + a.bottom - b.top - b.bottom) / 2), margin: getComputedStyle(node.querySelector("h3")).marginBottom};
          });
          assert(centers.difference < 1, `${lang} title/badge centers differ: ${centers.difference}`);
          assert.equal(centers.margin, "0px");
        }
      }
      await page.setViewportSize({width: 390, height: 844});
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), "Mobile guide overflow");
      await page.close();
    }
  } catch (error) {
    console.error('Browser handoff fixture state:', JSON.stringify({handoff, requests: requests.slice(-12)}));
    throw error;
  } finally {
    await context.close();
    await new Promise(resolve => server.close(resolve));
  }
}
module.exports = {runBrowserUpdateChecks};
