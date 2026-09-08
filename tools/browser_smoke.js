#!/usr/bin/env node
"use strict";

const {chromium, firefox, webkit} = require("playwright");
const {source: axeSource} = require("axe-core");
const {mkdir} = require("node:fs/promises");

const ACTION_TIMEOUT_MS = 20000;
const NAVIGATION_TIMEOUT_MS = 30000;
const FETCH_TIMEOUT_MS = 10000;
const RUN_TIMEOUT_MS = Number(process.env.BOTW_BROWSER_TEST_TIMEOUT_MS || 120000);
let currentStage = "initialisation";

function progress(browserName, stage) {
  currentStage = stage;
  console.log(JSON.stringify({status: "progress", browser: browserName, stage}));
}

async function closeWithTimeout(resource, label, timeout = 10000) {
  let timer;
  try {
    await Promise.race([
      resource.close(),
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(`Délai dépassé pendant ${label}`)), timeout);
      })
    ]);
  } finally {
    clearTimeout(timer);
  }
}

async function fetchJson(page, url, options = {}) {
  return page.evaluate(async ({requestUrl, requestOptions, timeout}) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(requestUrl, {...requestOptions, signal: controller.signal});
      return {ok: response.ok, body: await response.json()};
    } finally {
      clearTimeout(timer);
    }
  }, {requestUrl: url, requestOptions: options, timeout: FETCH_TIMEOUT_MS});
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function assertAccessible(page, context) {
  // L’injection par le protocole du navigateur ne relâche pas la politique CSP
  // stricte de l’application (script-src 'self').
  await page.evaluate(axeSource);
  const result = await page.evaluate(async () => window.axe.run(document, {
    runOnly: {
      type: "tag",
      values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]
    }
  }));
  if (!result.violations.length) return;
  const summary = result.violations.map(violation => {
    const nodes = violation.nodes.slice(0, 3)
      .map(node => `${node.target.join(" ")}: ${node.failureSummary}`)
      .join(" | ");
    return `${violation.id} (${violation.impact || "impact inconnu"}) — ${nodes}`;
  }).join("\n");
  throw new Error(`Audit d’accessibilité échoué (${context})\n${summary}`);
}

async function exerciseOnboarding(page) {
  const dialog = page.locator("#onboardingDialog");
  if (await dialog.isVisible()) {
    assert((await page.locator("#onboardingStepLabel").textContent()).includes("1 sur 3"),
      "L’assistant de premier lancement ne commence pas à la première étape");
    await assertAccessible(page, "assistant de premier lancement");
    await page.locator("#nextOnboarding").click();
    assert((await page.locator("#onboardingTitle").textContent()).includes("sauvegarde"),
      "La deuxième étape du premier lancement est absente");
    await page.locator("#nextOnboarding").click();
    assert((await page.locator("#onboardingTitle").textContent()).includes("Gyroscope"),
      "La présentation facultative du gyroscope est absente");
    await page.locator("#nextOnboarding").click();
    await dialog.waitFor({state: "hidden"});
    const preferences = await fetchJson(page, "/api/preferences");
    assert(preferences.body.values.onboarding_completed === true,
      "La fin du premier lancement n’est pas conservée");
  }

  await page.locator("#openHelp").click();
  await dialog.waitFor({state: "visible"});
  await page.keyboard.press("Escape");
  await dialog.waitFor({state: "hidden"});
  await page.waitForFunction(() => document.activeElement?.id === "openHelp");
}

async function captureBloodMoonReferences(page, browserName) {
  if (process.env.BOTW_CAPTURE_BLOOD_MOON !== "1") return;

  const outputDirectory = "test-results/blood-moon";
  await mkdir(outputDirectory, {recursive: true});
  const states = [
    {name: "unavailable", progress: 0, available: false},
    {name: "early", progress: 35, available: true},
    {name: "warning", progress: 75, available: true},
    {name: "critical", progress: 95, available: true},
    {name: "scheduled", progress: 100, available: true, scheduled: true},
    {name: "just-occurred", progress: 4, available: true, justOccurred: true}
  ];

  for (const state of states) {
    await page.evaluate(reference => {
      const panel = document.querySelector("#bloodMoonPanel");
      panel.classList.remove("scheduled", "unavailable", "just-occurred");
      panel.classList.toggle("scheduled", Boolean(reference.scheduled));
      panel.classList.toggle("unavailable", !reference.available);
      panel.classList.toggle("just-occurred", Boolean(reference.justOccurred));
      updateBloodMoonVisual(panel, {
        available: reference.available,
        scheduled: reference.scheduled,
        status: reference.justOccurred ? "just_occurred" : undefined,
        timer_progress_percent: reference.progress
      });
    }, state);
    await page.locator("#bloodMoonPanel").screenshot({
      animations: "disabled",
      path: `${outputDirectory}/${browserName}-${state.name}.png`
    });
  }
}

function isExpectedWebKitNavigationError(browserName, message) {
  // WebKit can expose an aborted fetch from the document being replaced as a
  // page error during reload.  Keep this exception deliberately narrow: only
  // the cache-busted DSU status poll is allowed, and the new document probes
  // the same endpoint explicitly immediately after the reload.
  return browserName === "webkit" &&
    message.includes("Fetch API cannot load") &&
    message.includes("/api/dsu?t=") &&
    message.includes("due to access control checks");
}

async function navigateToApplication(page, browserName) {
  for (let attempt = 1; attempt <= 2; attempt += 1) {
    try {
      // The application readiness probe below is the authoritative signal.
      // Waiting for DOMContentLoaded here is redundant and Firefox can keep
      // that lifecycle event pending on a fresh context even after the
      // document has committed and the local server is healthy.
      const response = await page.goto(page.baseUrl, {waitUntil: "commit"});
      assert(response?.ok(),
        `La navigation a répondu avec le statut HTTP ${response?.status() ?? "inconnu"}`);
      return;
    } catch (error) {
      const navigationTimedOut = error?.name === "TimeoutError";
      if (!navigationTimedOut || attempt === 2) throw error;
      console.log(JSON.stringify({
        status: "retry",
        browser: browserName,
        stage: currentStage,
        reason: "navigation_timeout",
        attempt: attempt + 1
      }));
      await page.waitForTimeout(250);
    }
  }
}

async function waitForApplication(page, browserName) {
  await navigateToApplication(page, browserName);
  await page.waitForFunction(() =>
    document.querySelector("#runtimePlatform").textContent !== "CHARGEMENT…" &&
    document.querySelectorAll("#categories [data-filter-type]").length > 0,
  null, {timeout: 45000});
}

async function runDesktop(browser, baseUrl, browserName) {
  const context = await browser.newContext({viewport: {width: 1440, height: 900}, acceptDownloads: true});
  context.setDefaultTimeout(ACTION_TIMEOUT_MS);
  context.setDefaultNavigationTimeout(NAVIGATION_TIMEOUT_MS);
  const page = await context.newPage();
  page.baseUrl = baseUrl;
  const errors = [];
  let documentReloadStarted = false;
  page.on("pageerror", error => {
    const message = String(error);
    if (!(documentReloadStarted &&
      isExpectedWebKitNavigationError(browserName, message))) errors.push(message);
  });
  page.on("response", response => {
    if (response.status() >= 500) errors.push(`${response.status()} ${response.url()}`);
  });
  progress(browserName, "bureau:chargement");
  await waitForApplication(page, browserName);
  await exerciseOnboarding(page);
  await assertAccessible(page, "tableau de bord");
  progress(browserName, "bureau:carte");

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
  assert((await page.locator("#completionBlockerSummary").textContent()).includes("empêchent le 100 %"),
    "La liste des éléments qui empêchent le 100 % n'est pas rendue");
  assert(await page.locator("#completionBlockerList li").count() > 0,
    "Le détail des catégories incomplètes est vide");

  const firstFilter = page.locator("#categories [data-filter-type]").first();
  await firstFilter.check();
  await page.waitForFunction(() => document.querySelectorAll("#list .item").length > 0);
  const rendered = await page.locator("#list .item").count();
  assert(rendered <= 300, `La liste rend ${rendered} lignes au lieu de 300 maximum`);
  assert(await page.locator("#markers .marker").count() > 0,
    "Le filtre sélectionné n'affiche aucun marqueur");
  const baseMarkerBox = await page.locator("#markers .baseMapMarker").first().boundingBox();
  assert(baseMarkerBox?.width >= 24 && baseMarkerBox?.height >= 24,
    `La cible d’un marqueur mesure ${baseMarkerBox?.width ?? 0} × ${baseMarkerBox?.height ?? 0}px`);
  const baseMarkerSemantics = await page.locator("#markers .baseMapMarker").first()
    .evaluate(element => ({tag: element.tagName, hidden: element.getAttribute("aria-hidden")}));
  assert(baseMarkerSemantics.tag === "SPAN" && baseMarkerSemantics.hidden === "true",
    "Un point dense ne doit pas dupliquer son bouton accessible de la liste");
  assert(await page.locator("#list .itemOpen").first().getAttribute("type") === "button",
    "La liste ne fournit pas le contrôle clavier équivalent au point cartographique");

  const zoomBefore = await page.evaluate(() => mapState.scale);
  await page.locator("#zoomIn").click();
  await page.waitForFunction(previous => mapState.scale > previous, zoomBefore);
  await page.locator("#mapReset").click();
  await page.waitForFunction(() => Math.abs(mapState.scale - mapState.minScale) < 0.000001);

  await page.locator("#list .itemOpen").first().click();
  await page.locator("#detailContent h2").waitFor({timeout: 10000});
  await assertAccessible(page, "fiche d’objectif");
  assert(await page.evaluate(() => selectedId !== null),
    "La fiche ouverte n'a pas conservé sa sélection cartographique");
  const selectedTrackingId = await page.evaluate(() => selectedId);
  await page.locator("#manualNoteInput").fill("Note conservée après annulation");
  await page.locator("#manualComplete").check();
  await page.waitForFunction(id => Boolean(manualTracking.entries[id]?.completed), selectedTrackingId);
  progress(browserName, "bureau:suivi-manuel");
  const manualResponse = await fetchJson(page, "/api/manual");
  const persistedManual = manualResponse.body.entries[selectedTrackingId]?.completed;
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
  progress(browserName, "bureau:itineraires");
  const routesRoundTrip = await page.evaluate(async timeout => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const exportedResponse = await fetch("/api/routes/export", {signal: controller.signal});
      const exported = await exportedResponse.json();
    const active = exported.sessions[exported.active_session_id];
    const response = await fetch("/api/routes/import", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
        body: JSON.stringify({session: active, expected_revision: exported.revision}),
        signal: controller.signal
    });
    return response.ok && Object.keys((await response.json()).sessions).length ===
      Object.keys(exported.sessions).length + 1;
    } finally {
      clearTimeout(timer);
    }
  }, FETCH_TIMEOUT_MS);
  assert(routesRoundTrip, "L'export/import d'itinéraire ne reproduit pas la session");

  progress(browserName, "bureau:dsu");
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

  progress(browserName, "bureau:rechargement");
  documentReloadStarted = true;
  await page.reload({waitUntil: "domcontentloaded"});
  await page.waitForFunction(id =>
    document.querySelector("#runtimePlatform").textContent !== "CHARGEMENT…" &&
    Boolean(manualTracking.entries[id]?.completed), selectedTrackingId, {timeout: 45000});
  const dsuAfterReload = await fetchJson(page, "/api/dsu");
  assert(dsuAfterReload.ok && typeof dsuAfterReload.body?.state === "string",
    "L'API DSU n'est pas accessible depuis le document rechargé");
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
  progress(browserName, "bureau:annulation-manuelle");
  const manualCheckbox = page.locator(
    `[data-manual-uncheck="${selectedTrackingId}"]`
  );
  const dialogPromise = page.waitForEvent("dialog", {timeout: ACTION_TIMEOUT_MS});
  // locator.uncheck() attend implicitement une éventuelle navigation. Firefox
  // peut conserver cette attente après la boîte confirm(), bien qu'aucune
  // navigation n'existe. Le clic DOM conserve le vrai événement utilisateur et
  // la vraie confirmation, sans ajouter cette attente de navigation étrangère.
  const clickPromise = manualCheckbox.evaluate(element => element.click());
  const dialog = await dialogPromise;
  const dialogMessage = dialog.message();
  await dialog.accept();
  await clickPromise;
  assert(
    dialog.type() === "confirm" &&
      dialogMessage.includes("Annuler la validation manuelle"),
    `Confirmation inattendue : ${dialogMessage}`
  );
  await page.waitForFunction(id => manualTracking.entries[id]?.completed === false,
    selectedTrackingId);
  const preservedNote = await page.evaluate(id => manualTracking.entries[id]?.note,
    selectedTrackingId);
  assert(preservedNote === "Note conservée après annulation",
    "L'annulation centralisée a supprimé la note personnelle");
  await captureBloodMoonReferences(page, browserName);
  if (errors.length) throw new Error(errors.join("\n"));
  progress(browserName, "bureau:fermeture");
  await closeWithTimeout(context, "la fermeture du contexte bureau");
  return {rendered, manual: true, routes: true, dsu: true};
}

async function runResponsive(browser, baseUrl, browserName) {
  const context = await browser.newContext({viewport: {width: 390, height: 844}});
  context.setDefaultTimeout(ACTION_TIMEOUT_MS);
  context.setDefaultNavigationTimeout(NAVIGATION_TIMEOUT_MS);
  const page = await context.newPage();
  page.baseUrl = baseUrl;
  progress(browserName, "responsive:chargement");
  await waitForApplication(page, browserName);
  await assertAccessible(page, "affichage mobile");
  const sidebar = page.getByRole("complementary");
  const content = page.getByRole("main");
  await Promise.all([sidebar.waitFor(), content.waitFor()]);
  const [sidebarBox, contentBox, viewportMeasurements] = await Promise.all([
    sidebar.boundingBox(),
    content.boundingBox(),
    page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      body: document.body.scrollWidth
    }))
  ]);
  const measurements = {
    ...viewportMeasurements,
    sidebar: sidebarBox?.width ?? 0,
    main: contentBox?.width ?? 0
  };
  const overflowCandidates = await page.evaluate(() =>
    Array.from(document.body.querySelectorAll("*")).flatMap(element => {
      if (element.clientWidth <= 0 || element.scrollWidth <= element.clientWidth + 2) return [];
      const label = element.id
        ? `#${element.id}`
        : `${element.tagName.toLowerCase()}${Array.from(element.classList)
          .slice(0, 2).map(name => `.${name}`).join("")}`;
      return [`${label}(${element.scrollWidth}/${element.clientWidth})`];
    }).slice(0, 8));
  assert(measurements.body <= measurements.viewport + 2,
    `Débordement horizontal responsive : ${measurements.body}px pour ${measurements.viewport}px; ` +
    `conteneurs suspects : ${overflowCandidates.join(", ") || "aucun"}`);
  assert(measurements.sidebar > 0 && measurements.main > 0,
    "Les zones principales disparaissent en affichage étroit");

  const narrowRegions = await page.locator("header, .hero").evaluateAll(elements =>
    elements.map(element => ({
      name: element.tagName.toLowerCase() === "header" ? "header" : ".hero",
      client: element.clientWidth,
      scroll: element.scrollWidth
    })));
  const overflowingRegion = narrowRegions.find(region => region.scroll > region.client + 2);
  assert(!overflowingRegion,
    overflowingRegion
      ? `${overflowingRegion.name} déborde en affichage étroit : ` +
        `${overflowingRegion.scroll}px pour ${overflowingRegion.client}px`
      : "Les régions principales respectent la largeur mobile");

  await page.locator("#toggleRoute").click();
  await page.waitForFunction(() => !document.querySelector("#routeBody").hidden);
  const routeWidth = await page.evaluate(() => document.body.scrollWidth);
  assert(routeWidth <= measurements.viewport + 2,
    `Le planificateur déborde en affichage étroit : ${routeWidth}px`);
  progress(browserName, "responsive:fermeture");
  await closeWithTimeout(context, "la fermeture du contexte responsive");
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
    firefox: () => firefox.launch({headless: true}),
    webkit: () => webkit.launch({headless: true})
  };
  if (!launchers[target]) throw new Error(`Navigateur inconnu : ${target}`);
  const watchdog = setTimeout(() => {
    console.error(JSON.stringify({
      status: "timeout",
      browser: target,
      stage: currentStage,
      timeout_ms: RUN_TIMEOUT_MS
    }));
    process.exit(124);
  }, RUN_TIMEOUT_MS);
  progress(target, "lancement");
  const browser = await launchers[target]();
  try {
    const desktop = await runDesktop(browser, url, target);
    await runResponsive(browser, url, target);
    console.log(JSON.stringify({status: "ok", browser: target, ...desktop, responsive: true}));
  } finally {
    progress(target, "navigateur:fermeture");
    await closeWithTimeout(browser, "la fermeture du navigateur");
    clearTimeout(watchdog);
  }
})().catch(error => { console.error(error); process.exit(1); });
