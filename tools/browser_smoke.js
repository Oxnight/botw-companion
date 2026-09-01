#!/usr/bin/env node
"use strict";

const {chromium, firefox} = require("playwright");

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function waitForApplication(page) {
  await page.goto(page.baseUrl, {waitUntil: "domcontentloaded"});
  await page.waitForFunction(() =>
    document.querySelector("#runtimePlatform").textContent !== "CHARGEMENT…" &&
    document.querySelectorAll("#categories [data-filter-type]").length > 0,
  null, {timeout: 45000});
}

async function runDesktop(browser, baseUrl) {
  const context = await browser.newContext({viewport: {width: 1440, height: 900}, acceptDownloads: true});
  const page = await context.newPage();
  page.baseUrl = baseUrl;
  const errors = [];
  page.on("pageerror", error => errors.push(String(error)));
  page.on("response", response => {
    if (response.status() >= 500) errors.push(`${response.status()} ${response.url()}`);
  });
  await waitForApplication(page);

  assert(await page.locator("#routeBody").getAttribute("hidden") !== null,
    "Le planificateur doit être masqué au lancement");
  assert(await page.locator("#categories input[type=checkbox]:checked").count() === 0,
    "Les filtres cartographiques doivent être décochés au lancement");
  assert(await page.locator("#markers .marker").count() === 0,
    "La carte doit être vide avant la sélection d'un filtre");
  assert((await page.locator("#bloodMoonCountdown").textContent()).trim() !== "-",
    "Le compteur de lune de sang n'est pas rendu");
  assert((await page.locator("#syncStatus").textContent()).includes("À jour"),
    "L'état de synchronisation n'est pas rendu");
  assert((await page.locator("#saveSlotTitle").textContent()).includes("Slot 1 • Mode normal"),
    "Les informations du slot sélectionné ne sont pas rendues");
  assert((await page.locator("#saveSlotDate").textContent()).includes("15/08/2026"),
    "La date du slot sélectionné n'est pas rendue");
  assert(await page.locator("#saveCaptionFallback").isVisible(),
    "Le remplacement accessible de caption.jpg doit rester visible lorsque l'image manque");

  const firstFilter = page.locator("#categories [data-filter-type]").first();
  await firstFilter.check();
  await page.waitForFunction(() => document.querySelectorAll("#list .item").length > 0);
  const rendered = await page.locator("#list .item").count();
  assert(rendered <= 300, `La liste rend ${rendered} lignes au lieu de 300 maximum`);
  assert(await page.locator("#markers .marker").count() > 0,
    "Le filtre sélectionné n'affiche aucun marqueur");

  const zoomBefore = await page.evaluate(() => mapState.scale);
  await page.locator("#zoomIn").click();
  await page.waitForFunction(previous => mapState.scale > previous, zoomBefore);
  await page.locator("#mapReset").click();
  await page.waitForFunction(() => Math.abs(mapState.scale - mapState.minScale) < 0.000001);

  await page.locator("#list .item").first().click();
  await page.locator("#detailContent h2").waitFor({timeout: 10000});
  assert(await page.evaluate(() => selectedId !== null),
    "La fiche ouverte n'a pas conservé sa sélection cartographique");
  const selectedTrackingId = await page.evaluate(() => selectedId);
  await page.locator("#manualNoteInput").fill("Note conservée après annulation");
  await page.locator("#manualComplete").check();
  await page.waitForFunction(id => Boolean(manualTracking.entries[id]?.completed), selectedTrackingId);
  const persistedManual = await page.evaluate(async id => {
    const response = await fetch("/api/manual");
    return (await response.json()).entries[id]?.completed;
  }, selectedTrackingId);
  assert(persistedManual === true, "Le suivi manuel n'est pas persisté par l'API");

  await page.locator("#detailRoute").click();
  await page.waitForFunction(() => routeState.entries.length === 1);
  await page.locator("#closeDetails").click();
  await page.waitForFunction(() => selectedId === null &&
    !document.querySelector("#itemDetails").classList.contains("open") &&
    document.querySelectorAll(".marker.selected").length === 0);

  await page.locator("#toggleRoute").click();
  assert(await page.locator("#routeBody").getAttribute("hidden") === null,
    "Le planificateur ne s'ouvre pas");
  const sessionCount = await page.locator("#routeSessionSelect option").count();
  await page.locator("#newRouteSession").click();
  await page.waitForFunction(previous =>
    document.querySelectorAll("#routeSessionSelect option").length === previous + 1, sessionCount);
  const routesRoundTrip = await page.evaluate(async () => {
    const exported = await (await fetch("/api/routes/export")).json();
    const active = exported.sessions[exported.active_session_id];
    const response = await fetch("/api/routes/import", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({session: active, expected_revision: exported.revision})
    });
    return response.ok && Object.keys((await response.json()).sessions).length ===
      Object.keys(exported.sessions).length + 1;
  });
  assert(routesRoundTrip, "L'export/import d'itinéraire ne reproduit pas la session");

  await page.waitForFunction(() => !document.querySelector("#toggleDsu").disabled);
  await page.locator("#toggleDsu").click();
  await page.waitForFunction(() => document.querySelector("#dsuStatus").textContent.includes("prêt"));
  await page.waitForFunction(() => document.querySelector("#dsuQuality").textContent === "Excellent");
  assert((await page.locator("#dsuReceivedRate").textContent()).includes("199.8 Hz"),
    "La fréquence gyro reçue n'est pas rendue");
  await page.locator("#dsuDiagnostic").evaluate(element => { element.open = true; });
  assert(await page.locator(".dsuMetrics").isVisible(),
    "Les mesures détaillées du gyroscope ne s'affichent pas");
  await page.locator("#toggleDsu").click();
  await page.waitForFunction(() => document.querySelector("#dsuStatus").textContent === "Désactivé");

  await page.reload({waitUntil: "domcontentloaded"});
  await page.waitForFunction(id =>
    document.querySelector("#runtimePlatform").textContent !== "CHARGEMENT…" &&
    Boolean(manualTracking.entries[id]?.completed), selectedTrackingId, {timeout: 45000});
  assert(await page.locator("#categories input[type=checkbox]:checked").count() === 0,
    "Un rechargement doit conserver une carte vide par défaut");
  await page.locator("#toggleManualReview").click();
  await page.locator(".manualReviewItem").first().waitFor();
  assert(await page.locator(".manualReviewItem").count() >= 1,
    "La liste centralisée n'affiche pas la validation manuelle");
  assert((await page.locator(".manualReviewItem").first().textContent())
    .includes("Note conservée après annulation"),
    "La note personnelle n'apparaît pas dans la liste centralisée");
  await page.locator(`[data-manual-open="${selectedTrackingId}"]`).click();
  await page.locator("#detailContent h2").waitFor({timeout: 10000});
  assert(await page.evaluate(id => selectedId === id, selectedTrackingId),
    "L'ouverture d'une fiche depuis les validations manuelles a échoué");
  await page.locator("#closeDetails").click();
  await page.locator("#toggleManualReview").click();
  page.once("dialog", dialog => dialog.accept());
  await page.locator(`[data-manual-uncheck="${selectedTrackingId}"]`).uncheck();
  await page.waitForFunction(id => manualTracking.entries[id]?.completed === false,
    selectedTrackingId);
  const preservedNote = await page.evaluate(id => manualTracking.entries[id]?.note,
    selectedTrackingId);
  assert(preservedNote === "Note conservée après annulation",
    "L'annulation centralisée a supprimé la note personnelle");
  if (errors.length) throw new Error(errors.join("\n"));
  await context.close();
  return {rendered, manual: true, routes: true, dsu: true};
}

async function runResponsive(browser, baseUrl) {
  const context = await browser.newContext({viewport: {width: 390, height: 844}});
  const page = await context.newPage();
  page.baseUrl = baseUrl;
  await waitForApplication(page);
  const measurements = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    body: document.body.scrollWidth,
    sidebar: document.querySelector(".sidebar").getBoundingClientRect().width,
    main: document.querySelector("main").getBoundingClientRect().width
  }));
  assert(measurements.body <= measurements.viewport + 2,
    `Débordement horizontal responsive : ${measurements.body}px pour ${measurements.viewport}px`);
  assert(measurements.sidebar > 0 && measurements.main > 0,
    "Les zones principales disparaissent en affichage étroit");
  await context.close();
}

(async () => {
  const url = process.argv[2] || "http://127.0.0.1:8765";
  const target = String(process.argv[3] || process.env.BOTW_BROWSER || "chromium").toLowerCase();
  const localChromium = process.env.BOTW_CHROMIUM_EXECUTABLE_PATH;
  const launchers = {
    chromium: () => chromium.launch({
      headless: true,
      ...(localChromium ? {executablePath: localChromium} : {})
    }),
    chrome: () => chromium.launch({headless: true, channel: "chrome"}),
    edge: () => chromium.launch({headless: true, channel: "msedge"}),
    firefox: () => firefox.launch({headless: true})
  };
  if (!launchers[target]) throw new Error(`Navigateur inconnu : ${target}`);
  const browser = await launchers[target]();
  try {
    const desktop = await runDesktop(browser, url);
    await runResponsive(browser, url);
    console.log(JSON.stringify({status: "ok", browser: target, ...desktop, responsive: true}));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });