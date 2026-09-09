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

async function saveDiagnosticScreenshot(page, browserName, name) {
  try {
    await mkdir("test-results/browser", {recursive: true});
    await page.screenshot({
      path: `test-results/browser/${browserName}-${name}.png`,
      animations: "disabled",
      fullPage: false
    });
  } catch (error) {
    console.warn(`Capture de diagnostic impossible (${name}) : ${error.message}`);
  }
}

async function assertAccessible(page, context) {
  // Browser-protocol injection does not weaken the CSP policy.
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
    return `${violation.id} (${violation.impact || "impact inconnu"}) - ${nodes}`;
  }).join("\n");
  throw new Error(`Audit d’accessibilité échoué (${context})\n${summary}`);
}

async function exerciseOnboarding(page) {
  const tutorial = page.locator("#tutorialLayer");
  const help = page.locator("#helpDialog");
  const businessStateBefore = await page.evaluate(() => ({
    syncInterval: document.querySelector("#syncInterval")?.value,
    syncPaused: document.querySelector("#pauseSync")?.getAttribute("aria-pressed"),
    routeHidden: document.querySelector("#routeBody")?.hasAttribute("hidden"),
    checkedFilters: document.querySelectorAll("#categories input[type=checkbox]:checked").length,
    dsuButtonLabel: document.querySelector("#toggleDsu")?.textContent
  }));
  const externalRequests = [];
  const observeRequest = request => {
    if (new URL(request.url()).origin !== new URL(page.baseUrl).origin) {
      externalRequests.push(request.url());
    }
  };
  page.on("request", observeRequest);

  if (await tutorial.isVisible()) {
    assert((await page.locator("#tutorialStepLabel").textContent()).includes("1 sur 9"),
      "Le parcours de premier lancement ne commence pas à la première des neuf étapes");
    assert((await page.locator("#tutorialSpotlight").boundingBox())?.width > 0,
      "La première cible du parcours n’est pas mise en évidence");
    await assertAccessible(page, "parcours de premier lancement");
    await page.locator("#nextTutorial").click();
    assert((await page.locator("#tutorialTitle").textContent()).includes("sauvegarde"),
      "La deuxième étape du premier lancement est absente");

    await page.evaluate(() => document.activeElement?.blur());
    await page.keyboard.press("Escape");
    await tutorial.waitFor({state: "hidden"});
    let preferences = await fetchJson(page, "/api/preferences");
    assert(preferences.body.values.tutorial_completed_version === undefined,
      "Fermer le parcours ne doit pas le marquer comme terminé");

    await page.locator("#openHelp").click();
    await help.waitFor({state: "visible"});
    assert(await page.locator("[data-help-chapter]").count() === 12,
      "Le centre d’aide ne contient pas ses douze chapitres");
    assert((await page.locator("#resumeTutorial").textContent()).includes("étape 2"),
      "Le parcours interrompu ne peut pas être repris à la bonne étape");
    await page.locator("#resumeTutorial").click();
    await tutorial.waitFor({state: "visible"});
    assert((await page.locator("#tutorialStepLabel").textContent()).includes("2 sur 9"),
      "La reprise du parcours a perdu la progression en mémoire");

    for (let expectedStep = 3; expectedStep <= 9; expectedStep += 1) {
      await page.locator("#nextTutorial").click();
      await page.waitForFunction(step =>
        document.querySelector("#tutorialStepLabel")?.textContent.includes(`${step} sur 9`),
      expectedStep);
    }
    await page.locator("#nextTutorial").click();
    await tutorial.waitFor({state: "hidden"});
    await page.waitForFunction(async () => {
      const response = await fetch("/api/preferences");
      const data = await response.json();
      return data.values.tutorial_completed_version === "1";
    });
    preferences = await fetchJson(page, "/api/preferences");
    assert(preferences.body.values.tutorial_completed_version === "1",
      "La version terminée du tutoriel n’est pas conservée");
    await help.waitFor({state: "visible"});
    await page.locator("#closeHelp").click();
    await help.waitFor({state: "hidden"});
  }

  await page.locator("#openHelp").click();
  await help.waitFor({state: "visible"});
  assert(await page.locator("[data-help-chapter]").count() === 12,
    "Le centre d’aide ne contient pas ses douze chapitres");
  await assertAccessible(page, "centre d’aide");
  await page.locator('[data-help-chapter="completion"]').click();
  assert((await page.locator("#helpContent h3").textContent()).includes("pourcentages"),
    "Un chapitre ne peut pas être ouvert depuis le sommaire");
  await page.locator("[data-start-chapter]").click();
  await tutorial.waitFor({state: "visible"});
  assert((await page.locator("#tutorialKind").textContent()).includes("CONTEXTUELLE"),
    "L’aide contextuelle d’un chapitre ne démarre pas");
  await page.locator("#closeTutorial").click();
  await help.waitFor({state: "visible"});
  await page.keyboard.press("Escape");
  await help.waitFor({state: "hidden"});
  await page.waitForFunction(() => document.activeElement?.id === "openHelp");
  page.off("request", observeRequest);
  assert(externalRequests.length === 0,
    `L’aide a effectué un appel externe inattendu : ${externalRequests.join(", ")}`);
  const businessStateAfter = await page.evaluate(() => ({
    syncInterval: document.querySelector("#syncInterval")?.value,
    syncPaused: document.querySelector("#pauseSync")?.getAttribute("aria-pressed"),
    routeHidden: document.querySelector("#routeBody")?.hasAttribute("hidden"),
    checkedFilters: document.querySelectorAll("#categories input[type=checkbox]:checked").length,
    dsuButtonLabel: document.querySelector("#toggleDsu")?.textContent
  }));
  assert(JSON.stringify(businessStateAfter) === JSON.stringify(businessStateBefore),
    "Le tutoriel a modifié un état métier de l’application");
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
  await page.locator("#updateBanner").waitFor({state: "visible"});
  const downloadUpdate = page.locator("#downloadUpdate");
  assert(await downloadUpdate.getAttribute("href") === null,
    "Le navigateur ne doit jamais recevoir un lien direct d'installation");
  // Windows exercises several browsers against one long-lived test server.
  // Later browsers therefore inherit the legitimate verified-download state.
  if (!(await downloadUpdate.isDisabled())) await downloadUpdate.click();
  await page.locator("#updateProgressText").filter({hasText: "terminé et vérifié"}).waitFor();
  assert(await page.locator("#updateProgressBar").evaluate(element => element.value) === 100,
    "Le téléchargement vérifié doit atteindre 100 %");
  await page.locator("#dismissUpdate").click();
  await page.locator("#updateBanner").waitFor({state: "hidden"});
  await page.locator("#checkUpdates").click();
  await page.locator("#updateBanner").waitFor({state: "visible"});
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
  const controlLayout = await page.evaluate(() => {
    const saveArea = document.querySelector(".syncSaveArea").getBoundingClientRect();
    const appArea = document.querySelector(".appActions").getBoundingClientRect();
    return {
      saveRight: saveArea.right,
      appLeft: appArea.left,
      refreshInSaveArea: Boolean(document.querySelector(".syncSaveArea #refresh")),
      helpInAppArea: Boolean(document.querySelector(".appActions #openHelp")),
      updatesInAppArea: Boolean(document.querySelector(".appActions #checkUpdates")),
      quitInAppArea: Boolean(document.querySelector(".appActions #quitCompanion"))
    };
  });
  assert(controlLayout.appLeft >= controlLayout.saveRight - 1,
    "Les zones Synchronisation et Application ne sont pas séparées sur bureau");
  assert(controlLayout.refreshInSaveArea && controlLayout.helpInAppArea &&
    controlLayout.updatesInAppArea && controlLayout.quitInAppArea,
  "Les commandes ne sont pas rangées dans leur zone fonctionnelle");
  const ringMeasurements = await page.evaluate(() => {
    const values = [
      [document.querySelector(".officialRing"), document.querySelector("#mapPercent"), "100.00 %"],
      [document.querySelector(".companionRing"), document.querySelector("#percent"), "100.0 %"]
    ];
    return values.map(([ring, value, sample]) => {
      const original = value.textContent;
      value.textContent = sample;
      const result = {
        ringWidth: ring.getBoundingClientRect().width,
        valueClientWidth: value.clientWidth,
        valueScrollWidth: value.scrollWidth
      };
      value.textContent = original;
      return result;
    });
  });
  assert(ringMeasurements.every(value =>
    value.ringWidth >= 136 && value.valueScrollWidth <= value.valueClientWidth + 1),
  `Valeur trop large pour un anneau : ${JSON.stringify(ringMeasurements)}`);
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
  // locator.uncheck() implicitly waits for possible navigation. Firefox may
  // keep waiting after confirm() even when no navigation exists. A DOM click
  // retains the real user event and confirmation without that unrelated wait.
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

  const stackedControls = await page.evaluate(() => {
    const saveArea = document.querySelector(".syncSaveArea").getBoundingClientRect();
    const appArea = document.querySelector(".appActions").getBoundingClientRect();
    return {
      saveBottom: saveArea.bottom,
      appTop: appArea.top,
      buttons: Array.from(document.querySelectorAll(".appActionButtons button"))
        .map(button => button.getBoundingClientRect().height)
    };
  });
  assert(stackedControls.appTop >= stackedControls.saveBottom - 1,
    "Les zones Synchronisation et Application ne s'empilent pas sur mobile");
  assert(stackedControls.buttons.every(height => height >= 44),
    `Une action Application mesure moins de 44 px : ${stackedControls.buttons.join(", ")}`);

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

  await page.locator("#openHelp").click();
  await page.locator("#helpDialog").waitFor({state: "visible"});
  await saveDiagnosticScreenshot(page, browserName, "responsive-help");
  const helpBounds = await page.locator("#helpDialog").boundingBox();
  assert(helpBounds && helpBounds.width <= 390 && helpBounds.height <= 844,
    "Le centre d’aide dépasse de l’affichage mobile");
  const helpLayout = await page.locator("#helpDialog").evaluate(dialog => {
    const regions = {
      header: dialog.querySelector(".helpHeader"),
      workspace: dialog.querySelector(".helpWorkspace"),
      navigation: dialog.querySelector(".helpNavigation"),
      content: dialog.querySelector(".helpContent"),
      actions: dialog.querySelector(".helpActions")
    };
    return Object.fromEntries(Object.entries(regions).map(([name, element]) => [name, {
      display: getComputedStyle(element).display,
      width: element.clientWidth,
      height: element.clientHeight,
      scrollHeight: element.scrollHeight
    }]));
  });
  const collapsedHelpRegion = Object.entries(helpLayout).find(([, region]) =>
    region.display === "none" || region.width === 0 || region.height === 0);
  assert(!collapsedHelpRegion,
    `Une zone du centre d’aide mobile est masquée : ${JSON.stringify(helpLayout)}`);
  assert(await page.locator("[data-help-chapter]").count() === 12,
    "Le sommaire mobile ne contient pas les douze chapitres");
  const applicationChapter = page.locator('[data-help-chapter="application"]');
  const mobileNavigation = page.locator(".helpNavigation");
  assert(helpLayout.navigation.scrollHeight > helpLayout.navigation.height,
    `La navigation mobile n’est pas défilable : ${JSON.stringify(helpLayout.navigation)}`);
  await mobileNavigation.evaluate(element => { element.scrollTop = element.scrollHeight; });
  await applicationChapter.waitFor({state: "visible"});
  await applicationChapter.press("Enter");
  const openedChapter = {
    current: await applicationChapter.getAttribute("aria-current"),
    heading: (await page.locator("#helpContent h3").textContent())?.trim(),
    focused: await page.evaluate(() => document.activeElement?.id)
  };
  assert(openedChapter.current === "page" &&
    openedChapter.heading === "Mises à jour, aide et fermeture" &&
    openedChapter.focused === "helpContent",
  `Le dernier chapitre ne s’ouvre pas au clavier : ${JSON.stringify(openedChapter)}`);
  progress(browserName, "responsive:aide-chapitre");
  await page.locator("[data-start-chapter]").click();
  await page.locator("#tutorialLayer").waitFor({state: "visible"});
  await page.waitForFunction(() => {
    const card = document.querySelector("#tutorialCard");
    return Boolean(card?.style.left && card?.style.top);
  });
  await saveDiagnosticScreenshot(page, browserName, "responsive-tutorial");
  const tutorialBounds = await page.locator("#tutorialCard").boundingBox();
  assert(tutorialBounds && tutorialBounds.x >= 0 && tutorialBounds.y >= 0 &&
    tutorialBounds.x + tutorialBounds.width <= 390 &&
    tutorialBounds.y + tutorialBounds.height <= 844,
  "Le parcours contextuel dépasse de l’affichage mobile");
  progress(browserName, "responsive:tutoriel-contextuel");
  await page.keyboard.press("Escape");
  await page.locator("#helpDialog").waitFor({state: "visible"});
  await page.locator("#closeHelp").click();
  await page.locator("#helpDialog").waitFor({state: "hidden"});

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
