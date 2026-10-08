const nativeFetch = window.fetch.bind(window);
const launchFragment = new URLSearchParams(window.location.hash.slice(1));
const sessionToken = document.querySelector("meta[name=\"botw-session-token\"]")?.content ||
    launchFragment.get("session") || "";

document.documentElement.dataset.inputModality = "pointer";
document.addEventListener("pointerdown", () => {
    document.documentElement.dataset.inputModality = "pointer";
}, true);
document.addEventListener("keydown", event => {
    if (!["Shift", "Control", "Alt", "Meta", "CapsLock"].includes(event.key)) {
        document.documentElement.dataset.inputModality = "keyboard";
    }
}, true);

if (window.location.hash) {
    history.replaceState(history.state, "", `${window.location.pathname}${window.location.search}`);
}

window.fetch = (input, options = {}) => {
    const requestUrl = new URL(input instanceof Request ? input.url : input, window.location.href);
    if (requestUrl.origin !== window.location.origin || !requestUrl.pathname.startsWith("/api/")) {
        return nativeFetch(input, options);
    }
    const headers = new Headers(
        options.headers || (input instanceof Request ? input.headers : undefined)
    );
    headers.set("X-BOTW-Session-Token", sessionToken);
    headers.set("X-BOTW-Language", document.documentElement.lang);
    return nativeFetch(input, { ...options, headers });
};

// Browser storage is optional: privacy settings or a full quota must not
// prevent the interface from starting or saving preferences on the server.
const browserStorage = (() => {
    const fallback = new Map();
    return {
        getItem(key) {
            if (fallback.has(key)) return fallback.get(key);
            try { return localStorage.getItem(key); } catch (_) { return null; }
        },
        setItem(key, value) {
            fallback.set(key, String(value));
            try { localStorage.setItem(key, String(value)); } catch (_) { /* Optional cache. */ }
        },
        removeItem(key) {
            fallback.set(key, null);
            try { localStorage.removeItem(key); } catch (_) { /* Optional cache. */ }
        }
    };
})();

let report = null, selectedId = null, filtersInitialized = false;
let saveCaptionRevision = null;
const detailCache = new Map();
let manualTracking = { schema_version: 2, revision: 0, updated_at: null, entries: {} };
let preferencesData = { schema_version: 1, revision: 0, updated_at: null, values: {} };
let preferenceSaveQueue = Promise.resolve();
let nativeLanguageSaved = false;
let onboardingShown = false, helpReturnFocus = null;
let helpChapterId = null, tutorialResume = null, tutorialInertState = [];
let tutorialState = null, tutorialPositionFrame = null, tutorialResizeObserver = null;
let tutorialTransition = null;
let tutorialReadyFrame = null;
let detailReturnTarget = null, manualReviewReturnFocus = null;
const SYNC_INTERVAL_KEY = "botw-companion-sync-interval";
const MAP_MODE_KEY = "botw-companion-map-formula";
const PROFILE_KEY = "botw-companion-completion-profile";
const MODE_FILTER_KEY = "botw-companion-game-mode-filter";
const DSU_SOURCE_KEY = "botw-companion-dsu-source";
const UPDATE_DISMISSED_KEY = "botw-companion-update-dismissed";
const UPDATE_INSTALL_NOTICE_KEY = "botw-companion-update-install-notice";
const UPDATE_CHECK_TIMEOUT_MS = 45000;
const TUTORIAL_VERSION = "2";
let syncTimer = null, syncPaused = false, syncInterval = Math.max(5, Number(browserStorage.getItem(SYNC_INTERVAL_KEY) || 30));
let heartbeatTimer = null;
let dsuTimer = null, dsuBusy = false;
let dsuRequest = null, documentLeaving = false;
function stopDsuPolling() {
    documentLeaving = true;
    clearTimeout(dsuTimer);
    dsuRequest?.abort();
}
window.addEventListener("botw:language-navigation", stopDsuPolling);
window.addEventListener("pagehide", stopDsuPolling);
window.addEventListener("pageshow", event => {
    if (!event.persisted) return;
    documentLeaving = false;
    delete document.documentElement.dataset.languageNavigation;
    refreshDsu();
});
let updateDownloadTimer = null;
let updatePrimaryBusy = false, updateInstallationPending = false;
window.BOTWBrowserSession.init(sessionToken, () => {
    updateInstallationPending = true;
    syncPaused = true;
    clearTimeout(syncTimer);
    clearTimeout(heartbeatTimer);
    clearTimeout(updateDownloadTimer);
    stopDsuPolling();
});
let availableUpdateVersion = null;
let runtimePlatform = {
    label: "Local system",
    native_dsu_engine: "DSU",
    relaunch_hint: "You can close this tab. Relaunch BOTW Companion to restart the application."
};
const LIST_PAGE_SIZE = 300;
let listRenderLimit = LIST_PAGE_SIZE;
const ROUTE_STORAGE_KEY = "botw-companion-route-v1", ROUTE_LIMIT = 1000;
let routePickStart = false;

function trustedGitHubReleaseUrl(value, kind) {
    try {
        const url = new URL(value);
        const prefix = kind === "download"
            ? "/Oxnight/botw-companion/releases/download/"
            : "/Oxnight/botw-companion/releases/tag/";
        return url.protocol === "https:" &&
            url.hostname === "github.com" &&
            url.port === "" &&
            url.username === "" &&
            url.password === "" &&
            url.search === "" &&
            url.hash === "" &&
            url.pathname.startsWith(prefix)
            ? url.href
            : null;
    } catch (_error) {
        return null;
    }
}

function dismissedUpdateVersion() {
    try {
        return sessionStorage.getItem(UPDATE_DISMISSED_KEY);
    } catch (_error) {
        return null;
    }
}

function rememberDismissedUpdate(version) {
    try {
        sessionStorage.setItem(UPDATE_DISMISSED_KEY, version);
    } catch (_error) {
    }
}

function showAvailableUpdate(data, manual = false) {
    const releaseUrl = trustedGitHubReleaseUrl(data.release_url, "release");
    if (!releaseUrl || typeof data.latest_version !== "string") {
        if (manual) toast("The update response is not valid", true);
        return;
    }
    if (!manual && dismissedUpdateVersion() === data.latest_version) return;
    $("#updateTitle").textContent = data.title || `BOTW Companion ${data.latest_version}`;
    $("#updateVersions").textContent =
        `Installed version: ${data.current_version} • New version: ${data.latest_version}`;
    availableUpdateVersion = data.latest_version;
    $("#downloadUpdate").disabled = false;
    $("#downloadUpdate").textContent = "Download the update";
    $("#updateReleaseNotes").href = releaseUrl;
    $("#updateBanner").hidden = false;
    refreshUpdateDownload();
}

function formatUpdateBytes(value) {
    const bytes = Math.max(0, Number(value) || 0);
    if (bytes < 1024) return `${Math.round(bytes)} o`;
    if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} Ko`;
    return `${(bytes / 1024 ** 2).toFixed(1)} Mo`;
}

function renderUpdateDownload(state) {
    if (updateInstallationPending) return;
    if (!state || typeof state.status !== "string") return;
    const active = ["checking", "downloading", "verifying"].includes(state.status);
    const progressVisible = state.status !== "inactive";
    const progress = Math.min(100, Math.max(0, Number(state.progress) || 0));
    $("#updateProgress").hidden = !progressVisible;
    $("#updateProgressBar").value = progress;
    $("#cancelUpdateDownload").hidden = !state.can_cancel;
    $("#retryUpdateDownload").hidden = !state.can_retry;
    $("#downloadUpdate").disabled = active || updatePrimaryBusy || updateInstallationPending ||
        (state.status === "ready_to_install" && !state.can_install);
    if (state.status === "ready_to_install") {
        $("#downloadUpdate").textContent = state.can_install
            ? "Install and restart"
            : "Verified download";
    } else if (active) {
        $("#downloadUpdate").textContent = state.status === "verifying" ? "Checking..." : "Downloading...";
    } else {
        $("#downloadUpdate").textContent = "Download the update";
    }
    const amount = state.bytes_total > 0
        ? `${formatUpdateBytes(state.bytes_received)} of ${formatUpdateBytes(state.bytes_total)} (${progress.toFixed(1)}%)`
        : "";
    const rate = state.bytes_per_second > 0
        ? ` • ${formatUpdateBytes(state.bytes_per_second)}/s`
        : "";
    $("#updateProgressText").textContent = [state.message, amount].filter(Boolean).join(" ") + rate;
    const installation = state.installation;
    if (installation && installation.status !== "inactive") {
        const notice = `${installation.status}:${installation.version || ""}:${installation.updated_at || ""}`;
        let previous = null;
        try { previous = sessionStorage.getItem(UPDATE_INSTALL_NOTICE_KEY); } catch (_error) {}
        if (notice !== previous && ["succeeded", "failed", "cancelled"].includes(installation.status)) {
            const logHint = installation.log_available && installation.log_path
                ? ` Log: ${installation.log_path}`
                : "";
            toast((installation.message || "Update status available") + logHint,
                installation.status !== "succeeded");
            try { sessionStorage.setItem(UPDATE_INSTALL_NOTICE_KEY, notice); } catch (_error) {}
        }
    }
    if (active) scheduleUpdateDownloadPoll();
}

function scheduleUpdateDownloadPoll() {
    clearTimeout(updateDownloadTimer);
    updateDownloadTimer = setTimeout(refreshUpdateDownload, 750);
}

async function refreshUpdateDownload() {
    try {
        const response = await fetch("/api/update/download");
        if (!response.ok) throw Error("service unavailable");
        renderUpdateDownload(await response.json());
    } catch (_error) {
        clearTimeout(updateDownloadTimer);
    }
}

async function updateDownloadAction(action) {
    const response = await fetch(`/api/update/download/${action}`, { method: "POST" });
    const state = await response.json();
    if (!response.ok) throw Error(state.erreur || "service unavailable");
    renderUpdateDownload(state);
    scheduleUpdateDownloadPoll();
}

async function startUpdateDownload() {
    try {
        await updateDownloadAction("start");
    } catch (_error) {
        toast("Download cannot start at this time", true);
    }
}

async function installVerifiedUpdate() {
    const platformMessage = runtimePlatform.id === "macos"
        ? "A separate macOS stable will check the DMG Apple Silicon, replace the app, " +
          "Then restart it. macOS can ask for your permission."
        : "The Windows wizard will then open and the application will restart after installation. " +
          "Windows will not be restarted.";
    if (updateInstallationPending || !confirm(
        "Install this update now?\n\n" +
        "BOTW Companion and JoyConDSU will shut down cleanly. " +
        platformMessage
    )) return false;
    updateInstallationPending = true;
    clearTimeout(updateDownloadTimer);
    const button = $("#downloadUpdate");
    button.disabled = true;
    button.textContent = "Preparing installation…";
    try {
        const response = await fetch("/api/update/install", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({client_id: window.BOTWBrowserSession.clientId})
        });
        const state = await response.json();
        if (!response.ok) throw Error(state.erreur || "service unavailable");
        $("#updateProgressText").textContent =
            state.message || "Secure shutdown before installation...";
        window.BOTWBrowserSession.installed(state.browser_handoff);
        return true;
    } catch (error) {
        updateInstallationPending = false;
        button.disabled = false;
        button.textContent = "Install and restart";
        toast(error.message || "Installation cannot start", true);
        return false;
    }
}

async function handleUpdatePrimaryAction() {
    if (updatePrimaryBusy || updateInstallationPending) return;
    updatePrimaryBusy = true;
    $("#downloadUpdate").disabled = true;
    try {
        const response = await fetch("/api/update/download");
        if (!response.ok) throw Error("service unavailable");
        const state = await response.json();
        if (state.status === "ready_to_install" && state.can_install) {
            await installVerifiedUpdate();
            return;
        }
        await startUpdateDownload();
    } catch (_error) {
        toast("The update cannot start at this time", true);
    } finally {
        updatePrimaryBusy = false;
        if (!updateInstallationPending) await refreshUpdateDownload();
    }
}

async function checkForUpdates(manual = false) {
    const button = $("#checkUpdates");
    const controller = new AbortController();
    // The local endpoint performs bounded retries against GitHub. Keep the UI
    // responsive while allowing that complete server-side budget to finish.
    const timer = setTimeout(() => controller.abort(), UPDATE_CHECK_TIMEOUT_MS);
    if (manual) {
        button.disabled = true;
        button.textContent = "Checking...";
    }
    try {
        let data;
        // The automatic check is otherwise silently lost after one local
        // network interruption. Retry a read once within the original budget.
        for (let attempt = 0; attempt < 2; attempt++) {
            let response;
            try {
                response = await fetch(`/api/update${manual ? "?force=1" : ""}`, {
                    signal: controller.signal
                });
                if (!response.ok) throw Error("service unavailable");
                data = await response.json();
                break;
            } catch (error) {
                if (attempt === 1 || controller.signal.aborted || response?.ok === false ||
                    error?.name !== "TypeError") throw error;
                await new Promise(resolve => setTimeout(resolve, 250));
                if (controller.signal.aborted) throw error;
            }
        }
        if (data.update_available === true) {
            showAvailableUpdate(data, manual);
        } else if (manual && data.status === "up_to_date") {
            toast("BOTW Companion is up to date");
        } else if (manual && data.status === "unsupported") {
            toast("Automatic verification is not available on this system", true);
        } else if (manual) {
            toast(data.message || "Unable to verify at the moment", true);
        }
    } catch (_error) {
        if (manual) {
            toast("Connection unavailable. BOTW Companion remains usable offline.", true);
        }
    } finally {
        clearTimeout(timer);
        if (manual) {
            button.disabled = false;
            button.textContent = "Updates";
        }
    }
}

function loadRouteState() {
    try {
        const value = JSON.parse(browserStorage.getItem(ROUTE_STORAGE_KEY) || "null");

        if (value?.schema_version === 1 && Array.isArray(value.entries)) {
            return value;
        }
    } catch (_error) {
    }

    return {
        schema_version: 1,
        name: "BOTW session",
        start: null,
        entries: [],
        updated_at: null
    };
}

let routeState = loadRouteState(), routesData = {
    schema_version: 3,
    revision: 0,
    updated_at: null,
    active_session_id: null,
    sessions: {}
};

let routeSaveQueue = Promise.resolve();
const selectedTypes = new Set();
const SHRINE_CHESTS_REMAINING_FILTER =
    "sanctuaires_termines_coffres_restants";

function preferenceValue(name, localKey, fallback) {
    return preferencesData.values[name] ??
        browserStorage.getItem(localKey) ?? fallback;
}

function savePreference(name, value) {
    preferencesData.values[name] = value;
    preferenceSaveQueue = preferenceSaveQueue
        .then(async () => {
            const response = await fetch("/api/preferences", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    values: { [name]: value },
                    expected_revision: preferencesData.revision
                })
            });
            const data = await response.json();
            if (!response.ok) {
                throw Error(data.erreur || "Unable to save preferences");
            }
            preferencesData = data;
        })
        .catch(error => toast(error.message, true));
    return preferenceSaveQueue;
}

const HELP_CHAPTERS = [
    {
        id: "privacy",
        title: "Privacy and offline mode",
        summary: "What stays on your device and what requires Internet access.",
        target: "header",
        points: [
            "Save analysis, the map, guides, manual tracking and routes work locally.",
            "Your game saves and personal Companion data are never sent to a remote service.",
            "A connection is used only when you request an update check or open an external source. A network failure does not block the Companion."
        ],
        tip: "The Companion’s local services only listen to 127.0.0.1, i.e. your own computer."
    },
    {
        id: "save",
        title: "save and Slot Analyzed",
        summary: "Understand the detection of Ryujinx or Cemu and the choice of the slot.",
        target: "#savePreview",
        points: [
            "The top panel shows the detected emulator, platform and active save slot.",
            "BOTW Companion compares supported save files and retains the most recent progress based on the game’s internal information.",
            "The preview, date and source help you check that you are viewing the expected save. Incomplete data never overwrites the last valid report."
        ],
        tip: "If the wrong part appears, check the emulator's save path and then use \"Read now\"."
    },
    {
        id: "sync",
        title: "Synchronization of the save",
        summary: "Interval, pause, immediate and historical reading.",
        target: ".syncSaveArea",
        points: [
            "Choose the interval at which the Companion checks whether the save has actually changed.",
            "“Pause” suspends automatic readings without stopping the application. “Read now” triggers an immediate check.",
            "Recent history distinguishes between a successful read, an unchanged save and a temporary error. The last valid result remains displayed on failure."
        ],
        tip: "Frequent checking does not speed up the emulator writing; 30 seconds is suitable in most cases."
    },
    {
        id: "completion",
        title: "The two percentages",
        summary: "Understand the difference between map completion and the completion profile.",
        target: ".hero",
        points: [
            "The official percentage reproduces BOTW’s map completion counter: Koroks, shrines, locations, towers, Divine Beasts and applicable DLC content.",
            "The completion profile is a broader indicator specific to the Companion and measures the objectives that the save automatically confirms.",
            "The two numbers do not have the same total or role, and the formula or profile selector allows you to examine the base set, the DLC and the specialized profiles."
        ],
        tip: "Expand “items preventing 100%” to see exactly what is missing from the selected profile."
    },
    {
        id: "sidebar",
        title: "Map filters and side navigation",
        summary: "Quickly choose the families of objectives displayed.",
        target: "#categories",
        points: [
            "The column to the left of the screen includes the big families: travel and places, quests and memories, treasures and other objectives.",
            "Each checkbox shows or hides an entire category. “All” selects every category, and “None” clears the selection.",
            "The counters on the right indicate the progress detected in each category. The caption at the bottom recalls the difference between doing, going, finished and informative."
        ],
        tip: "Start by checking one or two categories in the left column, and then use the detailed filters above the list."
    },
    {
        id: "navigation",
        title: "Detailed search and filters",
        summary: "Refine the selected categories in the left column.",
        target: ".toolbar",
        points: [
            "After choosing the categories in the left column, the search accepts a name, a region or a term present in a file.",
            "Filters separate states, additional content, game modes, locations, variants, and regions.",
            "A lens can be automatic, manual, mixed or informative. The scope banner indicates the limits of the active filter in order to avoid incorrect interpretation."
        ],
        tip: "Start with a category, then refine with the search: the map and the list use exactly the same perimeter."
    },
    {
        id: "map",
        title: "Hyrule map",
        summary: "Pan and zoom the map, use markers and open objective details.",
        target: ".mapPanel",
        points: [
            "Drag and drop the map, use the wheel or buttons to zoom, and the home button to return to the overview.",
            "Markers return the status of filtered objectives. Selecting a marker opens the same record as its entry in the list.",
            "Some objectives take place in an interior or do not have reliable coordinates: they remain accessible in the list without false location on Hyrule."
        ],
        tip: "The map and all its tiles are integrated into the application and remain available offline."
    },
    {
        id: "guides",
        title: "Objective details, evidence and guides",
        summary: "Read the status, solutions and their limitations.",
        target: ".listPanel",
        points: [
            "Each detail panel shows the detected status, available location, useful steps, rewards, chests and relevant conditions.",
            "Automatic proof comes from the save; it never asserts an action that the game data does not allow to distinguish.",
            "The guides may include external sources. Their consultation requires the Internet, but the essential content of the sheet is already embedded."
        ],
        tip: "Limit or manual validation statements are voluntary: they avoid turning a lack of evidence into a false result."
    },
    {
        id: "manual",
        title: "Manual tracking and data backups",
        summary: "Personal checkboxes, notes, import and export.",
        target: ".manualBar",
        points: [
            "Manual tracking completes the analysis without changing the official percentage or claiming to come from the game save.",
            "You can review validations, add notes, and remove a checkbox from the control panel.",
            "Exports allow you to transfer or save your validations and Companion data. An import checks the format before replacing the local data."
        ],
        tip: "Regularly “Save all data” if you plan to change computers."
    },
    {
        id: "routes",
        title: "Route planner",
        summary: "Create, order and maintain gaming sessions.",
        target: "#routePlanner",
        points: [
            "Add filtered results or a specific goal to a session, and then choose an optional starting point.",
            "Optimization can focus on direct distance, regions, or teleportation. Locked steps retain their position.",
            "The calculation is indicative: it does not simulate terrain, weather, climbing, enemies or resources consumed. Sessions can be duplicated, imported or exported."
        ],
        tip: "Lock mandatory steps before optimizing to keep the order of important appointments."
    },
    {
        id: "blood_moon",
        title: "Blood Looney",
        summary: "Interpret the internal counter and estimate.",
        target: "#bloodMoonPanel",
        points: [
            "The panel reads the counter recorded by BOTW and estimates the remaining active play time before the normal seven-day threshold.",
            "A moon can be programmed and then postponed if the conditions of the game do not allow the kinematics at midnight.",
            "The estimate depends on the last save read: a paused game, a menu or an unsaved period can explain a gap with real time."
        ],
        tip: "The percentage represents the progress of the known timer, not a random probability of triggering."
    },
    {
        id: "dsu",
        title: "Gyroscope JoyConDSU",
        summary: "Controller, calibration, diagnosis and emulator.",
        target: "#dsuControl",
        points: [
            "Select a compatible controller, then activate the engine only when your emulator needs to receive its movements.",
            "The diagnosis measures frequency, delay, jitter, loss and recalibration. Insufficient quality can come from Bluetooth, standby or another application using the controller.",
            "The emulator must be configured for the local DSU server 127.0.0.1:26760. The engine remains disabled by default and stops cleanly with the Companion."
        ],
        tip: "Set the controller to stand still during calibration and avoid running multiple DSU servers on the same port."
    },
    {
        id: "application",
        title: "Updates, help and closure",
        summary: "Manage the application without losing your data.",
        target: ".appActions",
        points: [
            "\"Updates\" consults the latest release compatible with a short time. The download starts only after confirmation, can resume after a cut and must be checked before any installation.",
            "The Help button reopens this center so you can resume the tour or open a chapter directly.",
            "Use “Quit” to cleanly shut down the local server and JoyConDSU. Personal data remains in the application’s data folder, separate from the installation."
        ],
        tip: () => runtimePlatform.data_directory
            ? `Local data and logs: ${runtimePlatform.data_directory}`
            : "Data and logs are kept in the application data folder, separate from the installed program."
    }
];

const ESSENTIAL_TUTORIAL_STEPS = [
    {
        chapter: "privacy",
        title: "Welcome to BOTW Companion",
        description: "The Companion analyzes your progress on this computer and remains usable without an Internet connection.",
        detail: "Your save is not sent. Only updates and external sources use the Internet, when you request them.",
        target: "header"
    },
    {
        chapter: "save",
        title: "Check the save retained",
        description: "The emulator, slot, date and preview confirm which save is being analyzed.",
        detail: () => {
            const save = report?.sauvegarde || {};
            return `${save.emulateur || "Detected Emulator"} • ${save.plateforme || runtimePlatform.label || "Local system"} • slot ${save.slot || "in the process of detection"}`;
        },
        target: "#savePreview"
    },
    {
        chapter: "sync",
        title: "Keep progress up to date",
        description: "Choose the save reading interval, pause synchronization or read the save immediately.",
        detail: "A temporary error never replaces the last valid report. Recent history explains each read.",
        target: ".syncSaveArea"
    },
    {
        chapter: "completion",
        title: "Two measures, two purposes",
        description: "The golden ring reproduces the official BOTW map; the green ring measures the automatically verifiable objectives of the chosen profile.",
        detail: "Their totals are different. Expands the blocking elements to understand precisely what is missing from the completion profile.",
        target: ".hero"
    },
    {
        chapter: "sidebar",
        title: "Select the categories in the left column",
        description: "The side navigation boxes show or hide entire families of objectives in the list and on the map.",
        detail: "Use “All” or “None” to quickly start from a complete or empty view. The counters and the legend summarize the progress of each family.",
        target: "#categories"
    },
    {
        chapter: "navigation",
        title: "Find out what interests you",
        description: "After selecting categories on the left, combine search and detailed filters to narrow down the objectives displayed in the list and on the map.",
        detail: "The automatic, manual, mixed and informative states remain distinct so as never to confuse a save proof with a personal box.",
        target: ".toolbar"
    },
    {
        chapter: "map",
        title: "Explore the map and objective details",
        description: "Move and zooms the map, then selects a marker or result to open its detailed sheet.",
        detail: "Internal or untrusted targets remain in the list rather than being arbitrarily placed on Hyrule.",
        target: ".mapPanel"
    },
    {
        chapter: "manual",
        title: "Keep your personal validations",
        description: "Manual tracking, notes and exports complete the automatic analysis without changing the official counter.",
        detail: "The planner located below then allows to group these objectives into sessions and optimize the indicative order.",
        target: ".manualBar"
    },
    {
        chapter: "blood_moon",
        title: "Anticipate the Blood Moon",
        description: "This panel interprets the timer in the last save and the game’s scheduling conditions.",
        detail: "The estimate follows the known active play time. A cinematic can be postponed if conditions are not met at midnight.",
        target: "#bloodMoonPanel"
    },
    {
        chapter: "dsu",
        title: "Activate the gyroscope only if necessary",
        description: "JoyConDSU is included, but remains disabled as long as your emulator doesn’t need the controller’s movements.",
        detail: "The Help button allows you to find all 13 chapters, including side filters, DSU configuration, routes, save files and updates.",
        target: "#dsuControl"
    }
];

function chapterById(id) {
    return HELP_CHAPTERS.find(chapter => chapter.id === id) || null;
}

function renderHelpNavigation() {
    $("#helpChapterList").innerHTML = HELP_CHAPTERS.map((chapter, index) =>
        `<button type="button" data-help-chapter="${esc(chapter.id)}">` +
        `<span>${String(index + 1).padStart(2, "0")}</span>${esc(chapter.title)}</button>`
    ).join("");
}

function updateHelpNavigation() {
    $("#helpOverview").classList.toggle("active", helpChapterId === null);
    $("#helpOverview").toggleAttribute("aria-current", helpChapterId === null);
    document.querySelectorAll("[data-help-chapter]").forEach(button => {
        const active = button.dataset.helpChapter === helpChapterId;
        button.classList.toggle("active", active);
        button.toggleAttribute("aria-current", active);
        if (active) button.setAttribute("aria-current", "page");
    });
}

function renderHelpOverview() {
    helpChapterId = null;
    updateHelpNavigation();
    $("#helpContent").innerHTML =
        `<p class="eyebrow">GOOD START</p>` +
        `<h3>Choose the level of help that suits you</h3>` +
        `<p>The essential tour introduces ten key areas of the interface. Detailed help chapters remain available here at any time.</p>` +
        `<div class="helpOverviewCards">` +
        `<article><b>Guided tour</b><span>10 contextual steps • about 3 minutes</span></article>` +
        `<article><b>Help center</b><span>13 complete chapters • fully offline</span></article>` +
        `</div>` +
        `<p class="helpPrivacyNote"><b>No action is triggered during the tour.</b> Items are only highlighted; your filters, validations, and save files are never changed.</p>`;
}

function renderHelpChapter(id, focus = true) {
    const chapter = chapterById(id);
    if (!chapter) {
        renderHelpOverview();
        return;
    }
    const tip = typeof chapter.tip === "function" ? chapter.tip() : chapter.tip;
    helpChapterId = id;
    updateHelpNavigation();
    $("#helpContent").innerHTML =
        `<p class="eyebrow">CHAPTER ${String(HELP_CHAPTERS.indexOf(chapter) + 1).padStart(2, "0")}</p>` +
        `<h3>${esc(chapter.title)}</h3>` +
        `<p>${esc(chapter.summary)}</p>` +
        `<ul>${chapter.points.map(point => `<li>${esc(point)}</li>`).join("")}</ul>` +
        `<p class="helpTip"><b>To remember</b>${esc(tip)}</p>` +
        `<button class="showHelpTarget" type="button" data-start-chapter="${esc(chapter.id)}">View in the interface</button>`;
    if (focus) $("#helpContent").focus({ preventScroll: true });
}

function updateResumeTutorialButton() {
    const button = $("#resumeTutorial");
    if (!tutorialResume) {
        button.hidden = true;
        return;
    }
    button.hidden = false;
    button.textContent = `Resume at step ${tutorialResume.index + 1}`;
}

function showHelp(chapterId = null, returnFocus = document.activeElement) {
    const dialog = $("#helpDialog");
    if (dialog.open || tutorialState) return;
    helpReturnFocus = returnFocus instanceof HTMLElement ? returnFocus : $("#openHelp");
    renderHelpNavigation();
    chapterId ? renderHelpChapter(chapterId, false) : renderHelpOverview();
    updateResumeTutorialButton();
    dialog.showModal();
    requestAnimationFrame(() => $("#helpTitle").focus({ preventScroll: true }));
}

function closeHelp(restoreFocus = true) {
    const dialog = $("#helpDialog");
    if (!dialog.open) return;
    dialog.close();
    if (restoreFocus) {
        const target = helpReturnFocus?.isConnected ? helpReturnFocus : $("#openHelp");
        target.focus({ preventScroll: true });
    }
}

function tutorialFocusableElements() {
    return [...$("#tutorialCard").querySelectorAll(
        "button:not([hidden]):not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex='-1'])"
    )].filter(element => element.getClientRects().length > 0);
}

function setTutorialBackgroundInert(active) {
    if (active) {
        tutorialInertState = [...document.body.children]
            .filter(element => element !== $("#tutorialLayer") && element.tagName !== "SCRIPT")
            .map(element => ({ element, inert: element.inert }));
        tutorialInertState.forEach(({ element }) => { element.inert = true; });
        return;
    }
    tutorialInertState.forEach(({ element, inert }) => { element.inert = inert; });
    tutorialInertState = [];
}

function currentTutorialStep() {
    return tutorialState?.steps[tutorialState.index] || null;
}

function visibleTutorialTarget(step) {
    if (!step?.target) return null;
    const target = document.querySelector(step.target);
    return target && target.getClientRects().length ? target : null;
}

function queueTutorialPosition() {
    if (!tutorialState) return;
    delete $("#tutorialCard").dataset.positionedStep;
    cancelAnimationFrame(tutorialReadyFrame);
    cancelAnimationFrame(tutorialPositionFrame);
    tutorialPositionFrame = requestAnimationFrame(() => {
        tutorialPositionFrame = requestAnimationFrame(positionTutorial);
    });
}

function setTutorialRectangle(element, left, top, width, height) {
    Object.assign(element.style, {
        left: `${Math.max(0, left)}px`,
        top: `${Math.max(0, top)}px`,
        width: `${Math.max(0, width)}px`,
        height: `${Math.max(0, height)}px`
    });
}

function tutorialRectangle(left, top, right, bottom) {
    return {
        left,
        top,
        right,
        bottom,
        width: Math.max(0, right - left),
        height: Math.max(0, bottom - top)
    };
}

function publishTutorialPosition(target) {
    const card = $("#tutorialCard"), session = tutorialState, index = session.index,
        rectangle = target?.getBoundingClientRect(),
        viewport = `${window.innerWidth}:${window.innerHeight}`;
    cancelAnimationFrame(tutorialReadyFrame);
    // Scrolling and ResizeObserver delivery can follow the layout calculation.
    // Publish readiness only after the target has kept the same geometry.
    tutorialReadyFrame = requestAnimationFrame(() => {
        tutorialReadyFrame = requestAnimationFrame(() => {
            if (tutorialState !== session || session.index !== index) return;
            const current = target?.getBoundingClientRect(),
                unchanged = !rectangle || ["left", "top", "width", "height"]
                    .every(key => Math.abs(rectangle[key] - current[key]) < .25);
            if (!unchanged || viewport !== `${window.innerWidth}:${window.innerHeight}`) {
                queueTutorialPosition();
                return;
            }
            card.dataset.positionedStep = String(index);
        });
    });
}

function createTutorialPreview(target) {
    const preview = $("#tutorialPreview"), clone = target.cloneNode(true),
        root = preview.shadowRoot || preview.attachShadow({ mode: "open" }),
        originals = [target, ...target.querySelectorAll("*")],
        copies = [clone, ...clone.querySelectorAll("*")], pseudoRules = [];
    // Isolate the frozen layout from application selectors. The preview is visual only:
    // it cannot submit forms, receive focus, or change the application's state.
    originals.forEach((original, index) => {
        const copy = copies[index], computed = getComputedStyle(original);
        for (const property of computed) {
            copy.style.setProperty(property, computed.getPropertyValue(property));
        }
        copy.style.setProperty("animation", "none");
        copy.style.setProperty("transition", "none");
        copy.removeAttribute("name");
        copy.removeAttribute("autofocus");
        copy.setAttribute("data-preview-node", String(index));
        for (const pseudo of ["::before", "::after"]) {
            const pseudoStyle = getComputedStyle(original, pseudo);
            if (!pseudoStyle.content || ["none", "normal"].includes(pseudoStyle.content)) continue;
            const declarations = Array.from(pseudoStyle, property =>
                `${property}:${pseudoStyle.getPropertyValue(property)};`).join("");
            pseudoRules.push(`[data-preview-node="${index}"]${pseudo}{${declarations}}`);
        }
        if (original instanceof HTMLInputElement) {
            copy.value = original.value;
            copy.checked = original.checked;
        } else if (original instanceof HTMLTextAreaElement
            || original instanceof HTMLSelectElement) {
            copy.value = original.value;
        } else if (original instanceof HTMLCanvasElement) {
            copy.getContext("2d")?.drawImage(original, 0, 0);
        }
        copy.scrollTop = original.scrollTop;
        copy.scrollLeft = original.scrollLeft;
    });
    clone.querySelectorAll("script").forEach(script => script.remove());
    Object.assign(clone.style, {
        position: "absolute", left: "0", top: "0", margin: "0",
        transform: "none", transformOrigin: "top left"
    });
    const style = document.createElement("style");
    style.textContent = pseudoRules.join("\n");
    root.replaceChildren(style, clone);
    preview.dataset.sourceSize = `${target.offsetWidth}:${target.offsetHeight}`;
    // Scroll offsets must be restored after insertion into the rendering tree.
    originals.forEach((original, index) => {
        copies[index].scrollTop = original.scrollTop;
        copies[index].scrollLeft = original.scrollLeft;
    });
    return clone;
}

function positionTutorialOverview(target, raw, viewportWidth, viewportHeight) {
    const card = $("#tutorialCard"), preview = $("#tutorialPreview"),
        margin = 12, gap = 16, padding = 9,
        sideBySide = viewportWidth >= 900,
        keepTargetLeft = sideBySide && target === document.querySelector("#categories"),
        availableWidth = sideBySide
            ? viewportWidth - card.offsetWidth - margin * 2 - gap
            : viewportWidth - margin * 2,
        availableHeight = sideBySide ? viewportHeight - margin * 2
            : Math.min((viewportHeight - margin * 2 - gap) * .42,
                raw.height * (availableWidth - padding * 2) / raw.width + padding * 2),
        scale = Math.min(1, Math.max(1, availableWidth - padding * 2) / raw.width,
            Math.max(1, availableHeight - padding * 2) / raw.height),
        width = raw.width * scale + padding * 2,
        height = raw.height * scale + padding * 2,
        slotLeft = sideBySide && !keepTargetLeft ? card.offsetWidth + margin + gap : margin,
        left = keepTargetLeft
            ? Math.min(slotLeft + availableWidth - width, Math.max(slotLeft, raw.left - padding))
            : slotLeft + (availableWidth - width) / 2,
        top = sideBySide ? (viewportHeight - height) / 2 : margin;
    preview.hidden = false;
    preview.style.width = `${raw.width * scale}px`;
    preview.style.height = `${raw.height * scale}px`;
    if (!preview.shadowRoot?.lastElementChild
        || preview.dataset.sourceSize !== `${target.offsetWidth}:${target.offsetHeight}`) {
        createTutorialPreview(target);
    }
    Object.assign(preview.shadowRoot.lastElementChild.style, {
        width: `${raw.width}px`, height: `${raw.height}px`,
        minWidth: `${raw.width}px`, maxWidth: `${raw.width}px`,
        minHeight: `${raw.height}px`, maxHeight: `${raw.height}px`,
        transform: `scale(${scale})`
    });
    preview.dataset.scale = String(scale);
    if (!sideBySide) card.style.maxHeight = `${Math.max(1,
        viewportHeight - margin * 2 - height - gap)}px`;
    card.style.left = `${sideBySide
        ? (keepTargetLeft ? viewportWidth - card.offsetWidth - margin : margin)
        : (viewportWidth - card.offsetWidth) / 2}px`;
    card.style.top = `${sideBySide ? (viewportHeight - card.offsetHeight) / 2
        : top + height + gap}px`;
    return tutorialRectangle(left, top, left + width, top + height);
}

function positionTutorial() {
    if (!tutorialState) return;
    const layer = $("#tutorialLayer"), card = $("#tutorialCard"),
        spotlight = $("#tutorialSpotlight"), target = visibleTutorialTarget(currentTutorialStep()),
        masks = [...layer.querySelectorAll(".tutorialMask")],
        viewportWidth = window.innerWidth, viewportHeight = window.innerHeight,
        margin = 12, gap = 16;
    card.style.maxHeight = "";
    $("#tutorialPreview").hidden = true;
    spotlight.classList.remove("tutorialSpotlight--overview");
    card.dataset.target = currentTutorialStep().target || "";
    card.dataset.layout = "direct";
    card.dataset.viewport = `${viewportWidth}:${viewportHeight}`;

    if (!target) {
        setTutorialRectangle(masks[0], 0, 0, viewportWidth, viewportHeight);
        masks.slice(1).forEach(mask => setTutorialRectangle(mask, 0, 0, 0, 0));
        spotlight.hidden = true;
        card.classList.add("tutorialCard--centered");
        card.style.left = `${Math.max(margin, (viewportWidth - card.offsetWidth) / 2)}px`;
        card.style.top = `${Math.max(margin, (viewportHeight - card.offsetHeight) / 2)}px`;
        publishTutorialPosition(null);
        return;
    }

    const raw = target.getBoundingClientRect(), padding = 9,
        left = raw.left - padding,
        top = raw.top - padding,
        right = raw.right + padding,
        bottom = raw.bottom + padding,
        targetRectangle = tutorialRectangle(left, top, right, bottom),
        width = targetRectangle.width, height = targetRectangle.height;

    card.classList.remove("tutorialCard--centered");

    const cardWidth = card.offsetWidth, cardHeight = card.offsetHeight,
        clampLeft = value => Math.min(
            Math.max(margin, value),
            Math.max(margin, viewportWidth - cardWidth - margin)
        ),
        clampTop = value => Math.min(
            Math.max(margin, value),
            Math.max(margin, viewportHeight - cardHeight - margin)
        ),
        candidates = [
            { left: left + width / 2 - cardWidth / 2, top: bottom + gap },
            { left: left + width / 2 - cardWidth / 2, top: top - cardHeight - gap },
            { left: right + gap, top: top + height / 2 - cardHeight / 2 },
            { left: left - cardWidth - gap, top: top + height / 2 - cardHeight / 2 }
        ].map((candidate, index) => ({
            left: clampLeft(candidate.left),
            top: clampTop(candidate.top),
            index
        })),
        overlap = (candidate, extra = 0) => {
            const overlapWidth = Math.max(0, Math.min(candidate.left + cardWidth, right + extra)
                - Math.max(candidate.left, left - extra));
            const overlapHeight = Math.max(0, Math.min(candidate.top + cardHeight, bottom + extra)
                - Math.max(candidate.top, top - extra));
            return overlapWidth * overlapHeight;
        };

    candidates.sort((first, second) =>
        overlap(first) - overlap(second) ||
        overlap(first, gap) - overlap(second, gap) ||
        first.index - second.index
    );
    card.style.left = `${candidates[0].left}px`;
    card.style.top = `${candidates[0].top}px`;
    const overview = overlap(candidates[0], gap) > 1 || left < margin || top < margin
        || right > viewportWidth - margin || bottom > viewportHeight - margin,
        focusRectangle = overview
            ? positionTutorialOverview(target, raw, viewportWidth, viewportHeight)
            : targetRectangle;
    if (overview) {
        card.dataset.layout = "overview";
        spotlight.classList.add("tutorialSpotlight--overview");
        setTutorialRectangle(masks[0], 0, 0, viewportWidth, viewportHeight);
        masks.slice(1).forEach(mask => setTutorialRectangle(mask, 0, 0, 0, 0));
    } else {
        setTutorialRectangle(masks[0], 0, 0, viewportWidth, focusRectangle.top);
        setTutorialRectangle(
            masks[1],
            focusRectangle.right,
            focusRectangle.top,
            viewportWidth - focusRectangle.right,
            focusRectangle.height
        );
        setTutorialRectangle(
            masks[2],
            0,
            focusRectangle.bottom,
            viewportWidth,
            viewportHeight - focusRectangle.bottom
        );
        setTutorialRectangle(
            masks[3],
            0,
            focusRectangle.top,
            focusRectangle.left,
            focusRectangle.height
        );
    }
    spotlight.hidden = false;
    setTutorialRectangle(
        spotlight,
        focusRectangle.left,
        focusRectangle.top,
        focusRectangle.width,
        focusRectangle.height
    );
    publishTutorialPosition(target);
}

function renderTutorialStep(focusHeading = false) {
    const step = currentTutorialStep(), total = tutorialState.steps.length,
        detail = typeof step.detail === "function" ? step.detail() : step.detail,
        last = tutorialState.index === total - 1,
        target = visibleTutorialTarget(step);
    delete $("#tutorialCard").dataset.positionedStep;
    $("#tutorialPreview").shadowRoot?.replaceChildren();
    $("#tutorialKind").textContent = tutorialState.kind === "essential"
        ? "ESSENTIAL TOUR"
        : "CONTEXTUAL HELP";
    $("#tutorialStepLabel").textContent = `Step ${tutorialState.index + 1} of ${total}`;
    $("#tutorialProgressBar").style.width = `${(tutorialState.index + 1) / total * 100}%`;
    $("#tutorialTitle").textContent = step.title;
    $("#tutorialDescription").textContent = step.description;
    $("#tutorialDetail").textContent = target
        ? detail
        : `${detail || ""} This part of the interface is not available in the current state, but the explanation remains accessible.`.trim();
    $("#previousTutorial").hidden = tutorialState.index === 0;
    $("#skipTutorial").hidden = tutorialState.kind !== "essential";
    $("#nextTutorial").textContent = last ? "Finish" : "Next";
    if (target) {
        target.scrollIntoView({
            behavior: "auto",
            block: "center",
            inline: "nearest"
        });
    }
    tutorialResizeObserver?.disconnect();
    tutorialResizeObserver?.observe($("#tutorialCard"));
    if (target) tutorialResizeObserver?.observe(target);
    queueTutorialPosition();
    if (focusHeading) requestAnimationFrame(() => $("#tutorialTitle").focus({ preventScroll: true }));
}

async function changeTutorialStep(index) {
    if (!tutorialState || tutorialTransition || index === tutorialState.index) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        tutorialState.index = index;
        renderTutorialStep(true);
        return;
    }
    const session = tutorialState, card = $("#tutorialCard"),
        spotlight = $("#tutorialSpotlight"), token = { animations: [] };
    tutorialTransition = token;
    card.dataset.transitioning = "true";
    card.setAttribute("aria-busy", "true");
    const animate = async (frames, duration) => {
        token.animations = [card, spotlight].map(element => element.animate(frames, {
            duration, easing: "cubic-bezier(.2,.7,.2,1)", fill: "both"
        }));
        await Promise.all(token.animations.map(animation => animation.finished.catch(() => {})));
    };
    try {
        await animate([{ opacity: 1 }, { opacity: 0 }], 100);
        if (tutorialState !== session || tutorialTransition !== token) return;
        session.index = index;
        renderTutorialStep();
        // Keep the outgoing view invisible until scrolling and layout have settled.
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        if (tutorialState !== session || tutorialTransition !== token) return;
        positionTutorial();
        token.animations.forEach(animation => animation.cancel());
        await animate([{ opacity: 0 }, { opacity: 1 }], 200);
    } finally {
        if (tutorialTransition === token) {
            token.animations.forEach(animation => animation.cancel());
            tutorialTransition = null;
            delete card.dataset.transitioning;
            card.removeAttribute("aria-busy");
            if (tutorialState === session) {
                positionTutorial();
                $("#tutorialTitle").focus({ preventScroll: true });
            }
        }
    }
}

function openTutorial(steps, options = {}) {
    if (!steps.length || tutorialState) return;
    const helpWasOpen = $("#helpDialog").open;
    if (helpWasOpen) closeHelp(false);
    tutorialState = {
        steps,
        index: Math.min(options.index || 0, steps.length - 1),
        kind: options.kind || "essential",
        returnToHelp: options.returnToHelp ?? helpWasOpen,
        helpChapterId: options.helpChapterId || helpChapterId,
        returnFocus: options.returnFocus instanceof HTMLElement
            ? options.returnFocus
            : (document.activeElement instanceof HTMLElement ? document.activeElement : $("#mainContent"))
    };
    tutorialResizeObserver = typeof ResizeObserver === "function"
        ? new ResizeObserver(queueTutorialPosition)
        : null;
    $("#tutorialLayer").hidden = false;
    setTutorialBackgroundInert(true);
    renderTutorialStep(true);
}

function startEssentialTutorial(resume = false, returnToHelp = false) {
    openTutorial(ESSENTIAL_TUTORIAL_STEPS, {
        kind: "essential",
        index: resume && tutorialResume ? tutorialResume.index : 0,
        returnToHelp,
        returnFocus: returnToHelp ? $("#openHelp") : $("#mainContent")
    });
}

function startChapterTutorial(id) {
    const chapter = chapterById(id);
    if (!chapter) return;
    const tip = typeof chapter.tip === "function" ? chapter.tip() : chapter.tip;
    openTutorial([{
        title: chapter.title,
        description: chapter.summary,
        detail: tip,
        target: chapter.target
    }], {
        kind: "chapter",
        returnToHelp: true,
        helpChapterId: id,
        returnFocus: $("#openHelp")
    });
}

async function closeTutorial({ persist = false, returnToHelp } = {}) {
    if (!tutorialState) return;
    const previous = tutorialState;
    tutorialState = null;
    cancelAnimationFrame(tutorialReadyFrame);
    tutorialTransition?.animations.forEach(animation => animation.cancel());
    tutorialTransition = null;
    delete $("#tutorialCard").dataset.transitioning;
    $("#tutorialCard").removeAttribute("aria-busy");
    $("#tutorialPreview").shadowRoot?.replaceChildren();
    cancelAnimationFrame(tutorialPositionFrame);
    tutorialResizeObserver?.disconnect();
    tutorialResizeObserver = null;
    $("#tutorialLayer").hidden = true;
    setTutorialBackgroundInert(false);
    if (previous.kind === "essential") {
        tutorialResume = persist ? null : { index: previous.index };
        if (persist && preferencesData.values.tutorial_completed_version !== TUTORIAL_VERSION) {
            await savePreference("tutorial_completed_version", TUTORIAL_VERSION);
        }
    }
    if (returnToHelp ?? previous.returnToHelp) {
        showHelp(previous.helpChapterId, previous.returnFocus);
    } else {
        previous.returnFocus?.focus({ preventScroll: true });
    }
}

function showOnboarding(force = false) {
    if (force) {
        showHelp();
        return;
    }
    onboardingShown = true;
    startEssentialTutorial(false, false);
}

async function migrateBrowserPreferences() {
    const candidates = {
        sync_interval: Number(browserStorage.getItem(SYNC_INTERVAL_KEY)),
        map_content_mode: browserStorage.getItem(MAP_MODE_KEY),
        completion_profile: browserStorage.getItem(PROFILE_KEY),
        game_mode_filter: browserStorage.getItem(MODE_FILTER_KEY)
    };
    const allowed = {
        sync_interval: [5, 10, 15, 30, 60],
        map_content_mode: ["automatique", "base", "dlc"],
        completion_profile: ["automatique", "base", "dlc", "amiibo", "expert", "automatic_only"],
        game_mode_filter: ["save", "all", "normal", "expert"]
    };
    const values = Object.fromEntries(
        Object.entries(candidates).filter(
            ([key, value]) =>
                preferencesData.values[key] == null &&
                allowed[key].includes(value)
        )
    );
    if (!Object.keys(values).length) {
        return;
    }
    const response = await fetch("/api/preferences", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            values,
            expected_revision: preferencesData.revision
        })
    });
    const data = await response.json();
    if (!response.ok) {
        throw Error(data.erreur || "Migration of preferences is impossible");
    }
    preferencesData = data;
}

function isCompletedShrineWithRemainingChest(x) {
    return x.categorie === "coffres_sanctuaires" &&
        x.sanctuaire_termine === true &&
        !x.termine;
}

function itemFilterTypes(x) {
    return [...new Set([
        x.filter_type,
        ...(x.content_filter_types || []),
        isCompletedShrineWithRemainingChest(x)
            ? SHRINE_CHESTS_REMAINING_FILTER
            : null
    ].filter(Boolean))]
}

function filterGroupsForDisplay() {
    const groups =
        report.filter_groups.map(group => ({
            ...group,
            types: [...group.types]
        }));
    const remaining =
        allItems().filter(
            isCompletedShrineWithRemainingChest
        );

    if (!remaining.length) {
        return groups;
    }

    const treasures =
        groups.find(group => group.id === "tresors");

    if (
        treasures &&
        !treasures.types.some(
            type =>
                type.id ===
                SHRINE_CHESTS_REMAINING_FILTER
        )
    ) {
        treasures.types.push({
            id: SHRINE_CHESTS_REMAINING_FILTER,
            label: "Completed Shrines - Remaining Chests",
            count: remaining.length
        });
        treasures.types.sort(
            (left, right) =>
                left.label.localeCompare(
                    right.label,
                    "en"
                )
        );
    }

    return groups;
}

function selectedTypeMatches(x) {
    return itemFilterTypes(x).some(type => selectedTypes.has(type))
}

const MAP_W = 1200, MAP_H = 1000;
const MAP_TILE_SIZE = 1024;
const MAP_TILE_LEVELS = [
    { id: "z1", width: 6000, height: 5000, density: 5 },
    { id: "z2", width: 12000, height: 10000, density: 10 },
    { id: "z3", width: 24000, height: 20000, density: 20 }
];
const mapTileNodes = new Map();
let activeMapTileLevel = null;

const mapState = {
    scale: 1,
    minScale: 1,
    x: 0,
    y: 0,
    ready: false,
    dragging: false,
    moved: false,
    startX: 0,
    startY: 0,
    originX: 0,
    originY: 0
};

const $ = s => document.querySelector(s),
    esc = s => String(s ?? "").replace(
        /[&<>"']/g,
        c => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;"
        }[c])
    );

function manualEntry(x) {
    return manualTracking.entries?.[itemId(x)] || {
        completed: false,
        note: ""
    }
}

function manualDone(x) {
    return Boolean(manualEntry(x).completed)
}

function combinedDone(x) {
    return Boolean(x.termine || manualDone(x))
}

function trackingMode(x) {
    return x.termine && manualDone(x)
        ? "mixed"
        : x.termine
            ? "automatic"
            : manualDone(x)
                ? "manual"
                : "none"
}

function trackingLabel(x) {
    return {
        mixed: "Automatic + manual",
        automatic: "Automatic",
        manual: "Manual",
        none: x.informational ? "Informational" : "To do"
    }[trackingMode(x)]
}

function stateClass(x) {
    return x.informational
        ? "info"
        : combinedDone(x)
            ? "done"
            : x.commence
                ? "doing"
                : "todo"
}

function itemId(x) {
    return x.tracking_id || x.categorie + ":" + (x.id || x.flag || x.name)
}

function allItems() {
    return [
        ...(report?.elements || []),
        ...(report?.map_layers || [])
    ]
}

function routeIds() {
    return new Set(routeState.entries.map(entry => entry.tracking_id))
}

function entrySnapshot(item) {
    return {
        name: item.name || item.display_name || item.id,
        category: item.categorie || null,
        region: item.region || null,
        x: item.x,
        z: item.z,
        content_origin: item.content_origin || null
    }
}

function routeResolvedEntries() {
    const items = new Map(
        allItems().map(item => [
            itemId(item),
            item
        ])
    );

    return routeState.entries.map((entry, index) => {
        const item = items.get(entry.tracking_id);

        return {
            entry,
            index,
            item:
                item && item.x != null && item.z != null
                    ? {
                        ...item,
                        tracking_id: entry.tracking_id,
                        locked: Boolean(entry.locked)
                    }
                    : null
        }
    });
}

function routePoints() {
    return routeResolvedEntries()
        .map(value => value.item)
        .filter(Boolean);
}

function saveRouteState() {
    routeState.updated_at = new Date().toISOString();

    routesData.sessions[routeState.id] = routeState;
    routesData.active_session_id = routeState.id;

    routeSaveQueue = routeSaveQueue
        .then(async () => {
            const payload = JSON.parse(JSON.stringify(routesData)),
                expectedRevision = routesData.revision;

            const response = await fetch(
                "/api/routes",
                {
                    method: "PUT",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        routes: payload,
                        expected_revision: expectedRevision
                    })
                }
            );

            const data = await response.json();

            if (!response.ok) {
                throw Error(
                    data.erreur ||
                    "Routes cannot be recorded"
                );
            }

            routesData.revision = data.revision;
            routesData.updated_at = data.updated_at;

            try {
                browserStorage.removeItem(ROUTE_STORAGE_KEY)
            } catch (_error) {
            }
        })
        .catch(error => {
            toast(error.message, true)
        });

    return routeSaveQueue;
}

function refreshVariants() {
    const select = $("#variant"),
        old = select.value;

    const variants = [
        ...new Set(
            allItems()
                .filter(selectedTypeMatches)
                .map(x => x.subtype)
                .filter(Boolean)
        )
    ].sort((a, b) => a.localeCompare(b, "en"));

    select.innerHTML =
        "<option value=\"all\">All variants</option>" +
        variants
            .map(x => `<option value="${esc(x)}">${esc(x)}</option>`)
            .join("");

    select.value = variants.includes(old) ? old : "all";
}

function originMatches(x, value) {
    const origin = x.content_origin || (x.dlc ? "master_trials" : "base");

    if (value === "all") {
        return true;
    }

    if (value === "expansion") {
        return [
            "expansion_bonus",
            "master_trials",
            "champions_ballad"
        ].includes(origin);
    }

    return origin === value;
}

function selectedGameMode() {
    const value = $("#gameMode").value;

    if (value === "save") {
        return report?.sauvegarde?.mode === "expert"
            ? "expert"
            : "normal";
    }

    return value;
}

function gameModeMatches(x) {
    const mode = selectedGameMode();

    return (
        mode === "all" ||
        x.game_mode_scope !== "expert_only" ||
        mode === "expert"
    );
}

function locationMatches(x) {
    const value = $("#location").value;

    if (value === "all") {
        return true;
    }

    if (
        [
            "map_and_list",
            "interior_only",
            "list_only"
        ].includes(value)
    ) {
        return x.display_scope === value;
    }

    return x.location_status === value;
}

function selectedMapScore() {
    const source = report.carte_officielle,
        choice = $("#mapDlcMode").value;

    const mode =
        choice === "automatique"
            ? source.selected_mode
            : choice;

    return {
        ...source,
        ...(source.scenarios?.[mode] || {}),
        selected_mode: mode,
        selection: choice
    };
}

function refreshProfileSelect() {
    const select = $("#completionProfile"),
        profiles = report.referentiel_100.profiles.filter(
            profile => profile.id !== "carte"
        );

    const stored = preferenceValue("completion_profile", PROFILE_KEY, null),
        fallback =
            report.referentiel_100.selection.save_mode === "expert"
                ? "expert"
                : "automatique";

    select.innerHTML = profiles
        .map(
            profile =>
                `<option value="${esc(profile.id)}" ${
                    profile.available === false ? "disabled" : ""
                }>${esc(profile.label)}${
                    profile.available === false
                        ? " - unavailable"
                        : ""
                }</option>`
        )
        .join("");

    const chosen = profiles.some(
        profile =>
            profile.id === (stored || fallback) &&
            profile.available !== false
    )
        ? (stored || fallback)
        : fallback;

    select.value = chosen;
}

function selectedCompletionScore() {
    const profile = report.referentiel_100.profiles.find(
        item => item.id === $("#completionProfile").value
    ),
        p = profile?.progress || {};

    if (!profile || profile.available === false) {
        return {
            available: false,
            label: profile?.label || "Profile",
            note: p.mode || "Profile unavailable"
        };
    }

    const formula = report.referentiel_100.formula.expression,
        inventory = report.referentiel_100.inventory_constraints,
        inventoryNote = profile.id === "amiibo"
            ? ` Separate collection: ${inventory.all_unique_armor} armor pieces exist for ${inventory.armor_inventory_limit} slots.`
            : "";
    return {
        available: true,
        label: profile.label,
        faits: p.faits || 0,
        total: p.total || 0,
        pourcentage: p.total
            ? 100 * p.faits / p.total
            : 0,
        note: `${profile.scope} Formula: ${formula}.${inventoryNote}`,
        blockers: p.blocking_categories || [], remaining: p.remaining || 0,
        effectiveProfile: p.effective_profile || profile.id, profileId: profile.id
    };
}

function renderCompletionBlockers(score) {
    const summary = $("#completionBlockerSummary"), list = $("#completionBlockerList"),
        details = $("#completionBlockers");
    if (!score.available) {
        summary.textContent = "Profile unavailable for this save";
        list.innerHTML = ""; details.open = false; return;
    }
    if (!score.remaining) {
        summary.textContent = "There is nothing to prevent the 100%";
        list.innerHTML = "<li>This profile is complete.</li>"; details.open = false; return;
    }
    summary.textContent = `${score.remaining.toLocaleString("en-US")} items prevent 100% completion`;
    list.innerHTML = score.blockers.map(category => {
        const examples = category.examples.map(item => esc(item.name)).join(" • "),
            more = Math.max(0, category.remaining - category.examples.length);
        return `<li><b>${esc(category.label)} : ${category.remaining.toLocaleString("en-US")}</b>` +
            `<span>${examples}${more ? ` • +${more.toLocaleString("en-US")} more` : ""}</span></li>`;
    }).join("");
}

function bloodMoonDuration(seconds) {
    if (
        seconds == null ||
        !Number.isFinite(Number(seconds))
    ) {
        return "-";
    }

    const total = Math.max(
        0,
        Math.ceil(Number(seconds))
    ),
        hours = Math.floor(total / 3600),
        minutes = Math.ceil((total % 3600) / 60);

    if (hours && minutes) {
        return `${hours} h ${minutes.toString().padStart(2, "0")} min`;
    }

    if (hours) {
        return `${hours} h`;
    }

    return `${Math.max(1, minutes)} min`;
}

const BLOOD_MOON_VISUAL_THRESHOLDS = [
    10, 20, 30, 40, 50, 60,
    70, 80, 90, 95, 100
];

function updateBloodMoonVisual(panel, moon) {
    if (!panel) return;

    const rawProgress = Number(moon?.timer_progress_percent),
        scheduled =
            Boolean(moon?.scheduled) ||
            moon?.status === "scheduled",
        available = Boolean(moon?.available),

        progress =
            available && Number.isFinite(rawProgress)
                ? Math.max(
                    0,
                    Math.min(100, rawProgress)
                )
                : 0,

        visualProgress = scheduled
            ? 100
            : progress,

        normalized = visualProgress / 100,

        rise = 9 - (7 * normalized),

        scale = .82 + (.16 * normalized),

        haloOpacity =
            .06 + (.84 * normalized),

        maliceOpacity =
            Math.max(
                0,
                Math.min(
                    1,
                    (visualProgress - 24) / 68
                )
            ),

        emberOpacity =
            Math.max(
                0,
                Math.min(
                    1,
                    (visualProgress - 68) / 32
                )
            ),

        saturation =
            .72 + (.56 * normalized),

        brightness =
            .72 + (.32 * normalized);

    panel.style.setProperty(
        "--moon-progress",
        visualProgress.toFixed(2)
    );

    panel.style.setProperty(
        "--moon-rise",
        `${rise.toFixed(2)}px`
    );

    panel.style.setProperty(
        "--moon-scale",
        scale.toFixed(3)
    );

    panel.style.setProperty(
        "--moon-halo-opacity",
        haloOpacity.toFixed(3)
    );

    panel.style.setProperty(
        "--moon-malice-opacity",
        maliceOpacity.toFixed(3)
    );

    panel.style.setProperty(
        "--moon-ember-opacity",
        emberOpacity.toFixed(3)
    );

    panel.style.setProperty(
        "--moon-saturation",
        saturation.toFixed(3)
    );

    panel.style.setProperty(
        "--moon-brightness",
        brightness.toFixed(3)
    );

    BLOOD_MOON_VISUAL_THRESHOLDS.forEach(
        (threshold) => {
            panel.classList.toggle(
                `moon-at-least-${threshold}`,
                visualProgress >= threshold
            );
        }
    );
}

function renderBloodMoon() {
    const moon = report?.lune_de_sang || {},
        panel = $("#bloodMoonPanel");

    panel.classList.toggle(
        "scheduled",
        Boolean(moon.scheduled) ||
        moon.status === "scheduled"
    );

    panel.classList.toggle(
        "unavailable",
        !moon.available
    );

    panel.classList.toggle(
        "just-occurred",
        moon.status === "just_occurred"
    );

    updateBloodMoonVisual(panel, moon);

    if (!moon.available) {
        $("#bloodMoonCountdown").textContent =
            "Estimation unavailable";

        $("#bloodMoonStatus").textContent =
            moon.status_label ||
            "Internal counter unavailable.";

        $("#bloodMoonPhase").textContent =
            "Unavailable";

        $("#bloodMoonPercent").textContent = "-";
        $("#bloodMoonThreshold").textContent = "-";
        $("#bloodMoonScheduled").textContent = "-";
        $("#bloodMoonEvent").textContent = "-";

        $("#bloodMoonMeasuredAt").textContent =
            "No measurements available";

        $("#bloodMoonInternal").textContent =
            "No value exploitable in the last save.";

        $("#bloodMoonAccuracy").textContent =
            moon.accuracy_label || "-";

        $("#bloodMoonProgress").style.width = "0%";

        return;
    }

    const duration = bloodMoonDuration(
        moon.active_seconds_until_event
    ),
        savedAt = localSaveTime(
            report?.synchronisation?.save_timestamp,
            report?.synchronisation?.save_timestamp_at
        );

    const phase =
        moon.scheduled
            ? "Validated cycle  =  programmed"
            : moon.status === "just_occurred"
                ? "New cycle"
                : "Current cycle  =  unscheduled";

    $("#bloodMoonCountdown").textContent =
        `≈ ${duration} of active play`;

    $("#bloodMoonPhase").textContent = phase;

    $("#bloodMoonPercent").textContent =
        `${Math.round(
            Number(moon.timer_progress_percent) || 0
        )} %`;

    $("#bloodMoonStatus").textContent =
        moon.scheduled
            ? "The blood moon is validated: it will be triggered at the next authorized midnight."
            : "Estimated time remaining since the last save before the actual trigger.";

    $("#bloodMoonThreshold").textContent =
        moon.scheduled
            ? "Reached"
            : `in ≈ ${bloodMoonDuration(
                moon.active_seconds_until_threshold
            )}`;

    $("#bloodMoonScheduled").textContent =
        moon.scheduled
            ? "Validated"
            : `in ≈ ${bloodMoonDuration(
                moon.active_seconds_until_scheduled
            )}`;

    $("#bloodMoonEvent").textContent =
        `in ≈ ${duration}`;

    $("#bloodMoonMeasuredAt").textContent =
        savedAt !== "-"
            ? `Exact value from the save at ${savedAt}`
            : "Exact measurement of the last save";

    $("#bloodMoonInternal").textContent =
        `Counter ${
            Number(moon.timer_value).toLocaleString(
                "en-US",
                {
                    maximumFractionDigits: 1
                }
            )
        } / ${
            Number(moon.timer_target).toLocaleString("en-US")
        } • game time ${moon.game_time_label}`;

    $("#bloodMoonAccuracy").textContent =
        `The counter decreases only during active play and is updated with each save.${
            moon.may_be_delayed
                ? " The trigger is currently subject to postponement."
                : ""
        }`;

    $("#bloodMoonProgress").style.width =
        `${Math.max(
            0,
            Math.min(
                100,
                Number(moon.timer_progress_percent) || 0
            )
        )}%`;
}

function worldPoint(x) {
    return {
        x: (Number(x.x) + 6000) / 10,
        y: (Number(x.z) + 5000) / 10
    }
}

function renderDsuSources(state) {
    const select = $("#dsuSource");
    const controllers = Array.isArray(state?.controllers) ? state.controllers : [];
    const preferred =
        state?.selected_source?.id ||
        select.value ||
        browserStorage.getItem(DSU_SOURCE_KEY) ||
        "";

    select.replaceChildren();
    if (!controllers.length) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "No controller detected";
        select.appendChild(option);
        select.value = "";
        $("#dsuCapabilities").textContent =
            "Connect a controller via USB or Bluetooth and wait for it to be detected.";
        return null;
    }

    for (const controller of controllers) {
        const option = document.createElement("option");
        option.value = String(controller.id);
        const suffix = controller.compatible
            ? " - gyroscope available"
            : controller.kind === "joycon_single"
                ? " Combine the two Joy-Cons."
                : " - gyroscope unavailable";
        option.textContent = `${controller.name}${suffix}`;
        option.dataset.compatible = controller.compatible ? "1" : "0";
        select.appendChild(option);
    }

    const chosen = controllers.find(x => String(x.id) === String(preferred)) ||
        controllers.find(x => x.compatible) ||
        controllers[0];
    select.value = String(chosen.id);
    browserStorage.setItem(DSU_SOURCE_KEY, String(chosen.id));

    const vidPid = controllerVidPid(chosen);
    const kind = chosen.kind === "joycon_pair"
        ? "Joy-Con pair / grip"
        : chosen.type || "Controller";
    $("#dsuCapabilities").textContent = chosen.compatible
        ? `${kind}${vidPid} • gyroscope and accelerometer available`
        : chosen.kind === "joycon_single"
            ? `${kind}${vidPid} • uses the combined Joy-Con pair`
            : `${kind}${vidPid} =  no gyroscope usable by SDL3`;
    return chosen;
}

function controllerVidPid(controller) {
    const vid = Number(controller?.vendor_id || 0);
    const pid = Number(controller?.product_id || 0);
    if (!vid && !pid) {
        return "";
    }
    return ` • ${vid.toString(16).padStart(4, "0").toUpperCase()}:${pid.toString(16).padStart(4, "0").toUpperCase()}`;
}

function dsuMetric(value, digits = 1, suffix = "") {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? `${numeric.toFixed(digits)}${suffix}` : "-";
}

function dsuCounter(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric.toLocaleString("en-US") : "-";
}

function renderDsuDiagnostic(state) {
    const diagnostic = state?.diagnostic || {
        status: "inactive",
        label: "Inactive diagnostic",
        summary: "Enable the gyroscope to measure signal quality."
    };
    const telemetry = state?.telemetry || {};
    const quality = $("#dsuQuality");
    quality.textContent = diagnostic.label;
    quality.className = `quality-${diagnostic.status}`;
    $("#dsuQualitySummary").textContent = diagnostic.summary;
    $("#dsuReceivedRate").textContent = dsuMetric(telemetry.received_hz, 1, " Hz");
    $("#dsuSentRate").textContent = Number(telemetry.clients || 0) === 0 && telemetry.sent_hz !== undefined
        ? "Waiting for the Emulator"
        : dsuMetric(telemetry.sent_hz, 1, " Hz");
    $("#dsuSampleAge").textContent = dsuMetric(telemetry.sample_age_ms, 1, " ms");
    $("#dsuReceivedJitter").textContent = telemetry.received_jitter_mean_ms === undefined
        ? "-"
        : `${dsuMetric(telemetry.received_jitter_mean_ms, 2, " ms")} avg. • ${dsuMetric(telemetry.received_jitter_max_ms, 2, " ms")} max.`;
    $("#dsuSentJitter").textContent = telemetry.sent_jitter_mean_ms === undefined
        ? "-"
        : `${dsuMetric(telemetry.sent_jitter_mean_ms, 2, " ms")} avg. • ${dsuMetric(telemetry.sent_jitter_max_ms, 2, " ms")} max.`;
    $("#dsuTimestampErrors").textContent = telemetry.duplicate_timestamps === undefined
        ? "-"
        : `${dsuCounter(telemetry.duplicate_timestamps)} duplicates • ${dsuCounter(telemetry.regressive_timestamps)} timestamps out of order`;
    $("#dsuSentPackets").textContent = dsuCounter(telemetry.sent_packets);
    $("#dsuNetworkErrors").textContent = telemetry.send_errors === undefined
        ? "-"
        : `${dsuCounter(telemetry.send_errors)} UDP • ${dsuCounter(telemetry.invalid_requests)} Invalid requests`;
    $("#dsuReconnects").textContent = telemetry.disconnects === undefined
        ? "-"
        : `${dsuCounter(telemetry.disconnects)} / ${dsuCounter(telemetry.reconnects)}`;
    $("#dsuCalibrations").textContent = telemetry.calibrations_valid === undefined
        ? "-"
        : `${dsuCounter(telemetry.calibrations_valid)} / ${dsuCounter(telemetry.calibrations_rejected)}`;
}

function renderDsu(state) {
    state = state || {
        state: "error",
        state_label: "Inaccessible DSU status",
        message: "The Companion cannot query the local server.",
        running: false
    };

    const selectedSource = renderDsuSources(state);
    $("#dsuDot").className = `dsu-${state.state}`;
    $("#dsuStatus").textContent = state.state_label;
    $("#dsuMessage").textContent = state.message;
    renderDsuDiagnostic(state);
    $("#dsuEngineLabel").textContent =
        state.engine_name || runtimePlatform.native_dsu_engine || "DSU";
    $("#dsuControl").title = [
        state.message,
        state.log_path ? `Log: ${state.log_path}` : null
    ].filter(Boolean).join("\n");
    $("#toggleDsu").textContent = state.running ? "Disable" : "Enable";
    $("#toggleDsu").classList.toggle("active", state.running);
    $("#dsuSource").disabled = dsuBusy || state.running;
    $("#toggleDsu").disabled =
        dsuBusy ||
        state.state === "unavailable" ||
        (!state.running && (!selectedSource || !selectedSource.compatible));
}

async function fetchStartupJson(url) {
    // Retry only transient read failures, never writes or HTTP rejections.
    // Keep the deadline active while reading the response body as well.
    let retryError;
    for (let attempt = 0; attempt < 2; attempt++) {
        if (documentLeaving && retryError) throw retryError;
        const controller = new AbortController();
        const deadline = setTimeout(() => controller.abort(), 10000);
        let response;
        try {
            response = await fetch(url, {signal: controller.signal});
            const data = await response.json();
            return {response, data};
        } catch (error) {
            if (attempt === 1 || documentLeaving || response?.ok === false ||
                !(error?.name === "TypeError" ||
                  (error?.name === "AbortError" && controller.signal.aborted))) throw error;
            retryError = error;
        } finally {
            clearTimeout(deadline);
        }
        await new Promise(resolve => setTimeout(resolve, 250));
    }
}

async function loadRuntimePlatform() {
    try {
        const {response, data} = await fetchStartupJson("/api/version");
        if (!response.ok) {
            throw Error("Platform unavailable");
        }
        runtimePlatform = {
            ...runtimePlatform,
            ...(data.platform || {})
        };
        $("#runtimePlatform").textContent =
            String(runtimePlatform.label || "Local system").toUpperCase();
        $("#dsuEngineLabel").textContent =
            runtimePlatform.native_dsu_engine || "DSU";
    } catch (_error) {
        $("#runtimePlatform").textContent = "LOCAL SYSTEM";
    }
}

async function copyText(text) {
    if (navigator.clipboard?.writeText) {
        try {
            await navigator.clipboard.writeText(text);
            return;
        } catch (_error) {
        }
    }

    const field = document.createElement("textarea");
    field.value = text;
    field.setAttribute("readonly", "");
    field.style.position = "fixed";
    field.style.opacity = "0";
    document.body.appendChild(field);
    field.select();
    const copied = document.execCommand("copy");
    field.remove();
    if (!copied) {
        throw Error("Unable to copy in this browser");
    }
}

function scheduleDsu(state) {
    clearTimeout(dsuTimer);
    if (documentLeaving || document.documentElement.dataset.languageNavigation === "true") return;
    const active = state?.running || ["starting", "waiting_controller", "ready"].includes(state?.state);
const seconds = document.hidden ? 30 : active ? 2 : 3;
    dsuTimer = setTimeout(refreshDsu, seconds * 1000);
}

async function refreshDsu() {
    if (documentLeaving || document.documentElement.dataset.languageNavigation === "true") return;
    const controller = new AbortController();
    dsuRequest?.abort();
    dsuRequest = controller;
    let state = null;
    try {
        const response = await fetch(`/api/dsu?t=${Date.now()}`, {signal: controller.signal});
        state = await response.json();
        if (!response.ok) {
            throw Error(state.message || "Inaccessible DSU status");
        }
        renderDsu(state);
    } catch (error) {
        if (controller.signal.aborted) return;
        renderDsu({
            state: "error",
            state_label: "Inaccessible DSU status",
            message: error.message,
            running: false
        });
    } finally {
        if (dsuRequest === controller) {
            dsuRequest = null;
            scheduleDsu(state);
        }
    }
}

async function toggleDsu() {
    if (dsuBusy) {
        return;
    }
    dsuBusy = true;
    $("#toggleDsu").disabled = true;
    const stop = $("#toggleDsu").classList.contains("active");
    let state = null;
    try {
        const sourceId = $("#dsuSource").value || null;
        const response = await fetch(`/api/dsu/${stop ? "stop" : "start"}`, {
            method: "POST",
            headers: stop ? {} : { "Content-Type": "application/json" },
            body: stop ? null : JSON.stringify({ source_id: sourceId })
        });
        state = await response.json();
        renderDsu(state);
        if (!response.ok) {
            throw Error(state.message || "DSU command failed");
        }
        toast(stop ? "Gyroscope disabled" : "DSU server enabled - leaves the controller motionless");
        scheduleDsu(state);
    } catch (error) {
        toast(error.message, true);
        state = null;
        await refreshDsu();
    } finally {
        dsuBusy = false;
        if (state) {
            renderDsu(state);
        }
    }
}

async function load(showToast = false) {
    if (documentLeaving || document.documentElement.dataset.languageNavigation === "true") return;
    $("#refresh").disabled = true;

    try {
        const [
            {response: reportResponse, data},
            {response: manualResponse, data: manual},
            {response: routesResponse, data: routes},
            {response: preferencesResponse, data: preferences}
        ] = await Promise.all([
            fetchStartupJson("/api/report?" + Date.now()),
            fetchStartupJson("/api/manual?" + Date.now()),
            fetchStartupJson("/api/routes?" + Date.now()),
            fetchStartupJson("/api/preferences?" + Date.now())
        ]);
        if (documentLeaving || document.documentElement.dataset.languageNavigation === "true") return;

        if (!preferencesResponse.ok) {
            throw Error(
                preferences.erreur ||
                "Inaccessible Preferences"
            );
        }

        preferencesData = preferences;
        const language = document.documentElement.lang === "en" ? "en" : "en";
        if (!nativeLanguageSaved) {
            const languageController = new AbortController();
            const languageDeadline = setTimeout(() => languageController.abort(), 4000);
            try {
                const languageResponse = await fetch("/api/language", {
                    method: "PUT",
                    signal: languageController.signal,
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ language })
                });
                const saved = await languageResponse.json();
                if (!languageResponse.ok) throw Error(saved.erreur);
                nativeLanguageSaved = true;
            } catch (error) {
                toast("The language for startup dialogs could not be saved.", true);
            } finally {
                clearTimeout(languageDeadline);
            }
        }
        if (
            preferencesData.values.tutorial_completed_version !== TUTORIAL_VERSION &&
            !onboardingShown
        ) {
            showOnboarding();
        }

        if (!reportResponse.ok) {
            throw Error(
                data.erreur ||
                "Analysis failed"
            );
        }

        if (!manualResponse.ok) {
            throw Error(
                manual.erreur ||
                "Manual tracking unavailable"
            );
        }

        if (!routesResponse.ok) {
            throw Error(
                routes.erreur ||
                "Inaccessible routes"
            );
        }

        const {response: catalogResponse, data: catalog} = await fetchStartupJson(
            "/api/catalog?revision=" +
            encodeURIComponent(
                data.report_revision_key
            )
        );

        if (!catalogResponse.ok) {
            throw Error(
                catalog.erreur ||
                "Catalog unavailable"
            );
        }

        if (
            catalog.report_revision_key !==
            data.report_revision_key
        ) {
            throw Error(
                "The save has changed during catalog loading; refreshes the page"
            );
        }

        if (
            report?.report_revision_key !==
            data.report_revision_key
        ) {
            detailCache.clear();
        }

        report = {
            ...data,
            elements: catalog.elements,
            map_layers: catalog.map_layers
        };

        manualTracking = manual;
        routesData = routes;
        await migrateBrowserPreferences();
        const savedInterval = Number(preferenceValue("sync_interval", SYNC_INTERVAL_KEY, 30));
        syncInterval = [5, 10, 15, 30, 60].includes(savedInterval) ? savedInterval : 30;
        routeState =
            routesData.sessions[
                routesData.active_session_id
            ];

        const legacy = loadRouteState();

        if (
            routeState.entries.length === 0 &&
            legacy.entries.length
        ) {
            routeState.entries =
                legacy.entries.map(
                    entry => ({
                        tracking_id:
                            entry.tracking_id,
                        locked:
                            Boolean(entry.locked),
                        snapshot: {}
                    })
                );

            routeState.start = legacy.start;
            routeState.name =
                legacy.name || routeState.name;

            await saveRouteState();

            toast(
                "Old route transferred in the application data"
            );
        }

        renderAll();

        if (showToast) {
            toast(
                "Back up and restore manual tracking and routes"
            );
        }
    } catch (e) {
        toast(e.message, true);
        updateSync(null, e.message);
    } finally {
        $("#refresh").disabled = false;
        scheduleSync();
    }
}

function renderAll() {
    const storedMode =
        preferenceValue("game_mode_filter", MODE_FILTER_KEY, "save");

    $("#gameMode").value =
        [
            "save",
            "all",
            "normal",
            "expert"
        ].includes(storedMode)
            ? storedMode
            : "save";

    const storedMapMode = preferenceValue(
        "map_content_mode",
        MAP_MODE_KEY,
        "automatique"
    );
    $("#mapDlcMode").value = [
        "automatique",
        "base",
        "dlc"
    ].includes(storedMapMode) ? storedMapMode : "automatique";

    $("#syncInterval").value = String(
        [5, 10, 15, 30, 60].includes(syncInterval)
            ? syncInterval
            : 30
    );

    refreshProfileSelect();

    const s = report.sauvegarde,
        score = selectedCompletionScore(),
        mapScore = selectedMapScore();

    const saveDate = localSaveDateTime(s.timestamp, s.date);

    $("#saveInfo").textContent =
        `Slot ${s.slot} • ${
            s.mode === "expert"
                ? "Master Mode"
                : "Normal Mode"
        } • ${saveDate} • ${s.chemin}`;

    renderSavePreview(s, saveDate);

    const emulatorLabel = String(s.emulateur || "Emulator").toUpperCase();
    const runtimeEmulator = $("#runtimeEmulator");
    if (runtimeEmulator) runtimeEmulator.textContent = emulatorLabel;

    renderBloodMoon();

    $("#mapPercent").textContent =
        mapScore.pourcentage_affiche;

    $(".officialRing").style.setProperty(
        "--progress",
        mapScore.pourcentage + "%"
    );

    $("#mapScore").textContent =
        `${mapScore.faits.toLocaleString("en-US")} Markers on ${mapScore.total.toLocaleString("en-US")}`;

    const formula =
        mapScore.selected_mode === "dlc"
            ? "Base game + DLC formula"
            : "Formula basic game";

    $("#mapStatus").textContent =
        mapScore.visible_dans_le_jeu
            ? `Official percentage of the map currently visible in BOTW. ${formula}${
                mapScore.selection === "automatique"
                    ? " selected automatically."
                    : " imposed manually."
            }`
            : `Exact prediction of map completion. This counter stays hidden in BOTW until you first defeat Ganon. ${formula}${
                mapScore.selection === "automatique"
                    ? " selected automatically."
                    : " imposed manually."
            }`;

    const labels = {
        korogus: "Koroks",
        sanctuaires_base: "Shrines",
        marqueurs_carte:
            "Places + towers + creatures",
        sanctuaires_dlc:
            "Shrines DLC",
        donjon_final_dlc:
            "Final DLC dungeon"
    };

    $("#mapBreakdown").innerHTML =
        Object.entries(mapScore.components)
            .map(
                ([k, c]) =>
                    `<span>${esc(
                        labels[k] || k
                    )} <b>${c.faits}/${c.total}</b></span>`
            )
            .join("");

    $("#percent").textContent =
        score.available
            ? score.pourcentage.toFixed(1) + " %"
            : "-";

    $(".companionRing").style.setProperty(
        "--progress",
        (score.pourcentage || 0) + "%"
    );

    $("#score").textContent =
        score.available
            ? `${score.faits.toLocaleString("en-US")} completed items out of ${score.total.toLocaleString("en-US")}`
            : `${score.label} Unavailable for this save`;

    $("#scoreNote").textContent = score.note;
    renderCompletionBlockers(score);

    const pick = score.effectiveProfile === "amiibo"
        ? ["armures", "armures_max", "equipements_particuliers", "harnachements"]
        : ["sanctuaires", "korogus", "quetes_principales", "compendium"];

    $("#quickStats").innerHTML =
        pick.map(k => {
            const c = report.categories[k],
                scoped = report.elements.filter(item =>
                    item.categorie === k && item.score_profiles.includes(score.effectiveProfile)
                ),
                done = scoped.filter(item => item.termine).length;
            return scoped.length
                ? `<span>${esc(c.label)} <b>${done}/${scoped.length}</b></span>` : "";
        }).join("");

    renderManualSummary();
    updateSync(report.synchronisation);
    renderFilterNav();

    const regions = [
        ...new Set(
            allItems()
                .map(x => x.region)
                .filter(Boolean)
        )
    ].sort();

    const old = $("#region").value;

    $("#region").innerHTML =
        "<option value=\"all\">All regions</option>" +
        regions
            .map(x => `<option>${esc(x)}</option>`)
            .join("");

    $("#region").value =
        regions.includes(old)
            ? old
            : "all";

    renderItems();
    renderRoute();

    if (!mapState.ready) {
        requestAnimationFrame(resetMap);
    }

}

function renderSavePreview(save, saveDate) {
    const mode = save.mode === "expert" ? "Master Mode" : "Normal Mode",
        emulator = save.emulateur || "Emulator",
        platform = save.plateforme || runtimePlatform.label || "Local system",
        revision = String(report.report_revision_key || `${save.slot}:${save.date}`),
        image = $("#saveCaption"),
        fallback = $("#saveCaptionFallback");

    $("#saveSlotTitle").textContent = `Slot ${save.slot} • ${mode}`;
    $("#saveSlotDate").textContent = `Latest save: ${saveDate}`;
    $("#saveSlotSource").textContent = `${emulator} • ${platform}`;
    $("#savePreview").title = save.detection_mode || "Slot selected automatically";
    fallback.textContent = `SLOT ${save.slot}`;

    if (saveCaptionRevision === revision) {
        return;
    }

    saveCaptionRevision = revision;
    image.hidden = true;
    fallback.hidden = false;
    image.alt = `Preview of slot ${save.slot}, ${mode} mode, saved on ${saveDate}`;
    image.dataset.revision = revision;
    image.onload = () => {
        if (image.dataset.revision === revision) {
            image.hidden = false;
            fallback.hidden = true;
        }
    };
    image.onerror = () => {
        if (image.dataset.revision === revision) {
            image.hidden = true;
            fallback.hidden = false;
        }
    };
    image.src = `/api/save-caption?revision=${encodeURIComponent(revision)}`;
}

function syncDate(value) {
    return value
        ? new Date(value).toLocaleTimeString(
            "en-US",
            {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit"
            }
        )
        : "-"
}

function localSaveDateTime(timestamp, fallback = null) {
    const numeric = Number(timestamp);
    const date = Number.isFinite(numeric) && numeric > 0
        ? new Date(numeric * 1000)
        : (fallback ? new Date(fallback) : null);
    if (!date || Number.isNaN(date.getTime())) return "-";
    const localDate = new Intl.DateTimeFormat("en-US", {
        dateStyle: "short"
    }).format(date);
    const localTime = new Intl.DateTimeFormat("en-US", {
        timeStyle: "medium"
    }).format(date);
    return `${localDate} at ${localTime}`;
}

function localSaveTime(timestamp, fallback = null) {
    const numeric = Number(timestamp);
    const date = Number.isFinite(numeric) && numeric > 0
        ? new Date(numeric * 1000)
        : (fallback ? new Date(fallback) : null);
    if (!date || Number.isNaN(date.getTime())) return "-";
    return new Intl.DateTimeFormat("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
    }).format(date);
}

function updateSync(meta, error = null) {
    meta = meta || {};

    const status =
        error
            ? "erreur"
            : meta.status || "initialisation";

    $("#syncStatus").textContent =
        error
            ? "Synchronization temporarily unavailable"
            : meta.status_label ||
                "First Reading Pending";

    $("#syncDot").className =
        `sync-${status}`;

    const mode =
        meta.save_mode === "expert"
            ? "Master Mode"
            : meta.save_mode === "normal"
                ? "normal"
                : "-";

    const candidate =
        meta.candidate_slot
            ? ` • candidate ${meta.candidate_slot}`
            : "";

    $("#syncTimes").textContent =
        error
            ? `${error} • last report retained`
            : `Last successful read at ${syncDate(meta.last_success_at)} • internal save at ${localSaveTime(meta.save_timestamp, meta.save_timestamp_at)} • slot ${meta.slot || "-"} (${mode})${candidate} • revision ${meta.report_revision || 0}`;

    const events = meta.events || [];

    $("#syncEvents").innerHTML =
        events.length
            ? events
                .map(
                    event =>
                        `<p><time>${esc(syncDate(event.at))}</time><span>${esc(event.message)}</span></p>`
                )
                .join("")
            : "<p>No event.</p>";
}

function scheduleSync() {
    clearTimeout(syncTimer);

    if (syncPaused) {
        return;
    }

    const effectiveInterval =
        document.hidden
            ? Math.max(180, syncInterval)
            : syncInterval;

    syncTimer = setTimeout(
        () => checkSync(false),
        effectiveInterval * 1000
    );
}

async function sendHeartbeat() {
    if (updateInstallationPending) return;
    try {
        await fetch(
            "/api/heartbeat",
            {
                method: "POST",
                keepalive: true
            }
        )
    } catch (_error) {
    }

    clearTimeout(heartbeatTimer);

    heartbeatTimer = setTimeout(
        sendHeartbeat,
        document.hidden
            ? 60000
            : 30000
    );
}

async function quitCompanion() {
    if (
        !confirm(
            "Stop BOTW Companion? Manual tracking and previously recorded routes will be retained."
        )
    ) {
        return;
    }

    clearTimeout(syncTimer);
    clearTimeout(heartbeatTimer);
    clearTimeout(dsuTimer);

    try {
        await fetch(
            "/api/shutdown",
            {
                method: "POST"
            }
        )
    } catch (_error) {
    }

    document.body.innerHTML =
        `<main class="shutdownPage"><div class="panel"><h1>BOTW Companion has stopped</h1><p>${esc(runtimePlatform.relaunch_hint)}</p></div></main>`;
}

async function checkSync(force = false) {
    $("#refresh").disabled = true;

    if (force) {
        updateSync({
            status: "analyse",
            status_label:
                "Immediate reading required",
            events:
                report?.synchronisation?.events || []
        });
    }

    try {
        const response = await fetch(
            `/api/sync?force=${force ? 1 : 0}&t=${Date.now()}`
        ),
            data = await response.json();

        if (!response.ok) {
            throw Error(
                data.erreur ||
                "Synchronization failed"
            );
        }

        if (data.changed) {
            await load(false);

            toast(
                "New save analyzed and updated catalog"
            );
        } else {
            updateSync(data.synchronisation);

            if (force) {
                toast(
                    "Re-read save - unchanged content"
                );
            }
        }
    } catch (error) {
        updateSync(
            report?.synchronisation,
            error.message
        );
    } finally {
        $("#refresh").disabled = false;
        scheduleSync();
    }
}

function renderFilterNav() {
    const displayGroups =
        filterGroupsForDisplay();
    const available = new Set(
        displayGroups.flatMap(
            group =>
                group.types.map(
                    type => type.id
                )
        )
    );

    if (!filtersInitialized) {
        filtersInitialized = true;
    } else {
        [...selectedTypes].forEach(type => {
            if (!available.has(type)) {
                selectedTypes.delete(type);
            }
        });
    }

    const scoped = allItems().filter(
        x =>
            gameModeMatches(x) &&
            locationMatches(x)
    );

    const scopedByType = new Map();

    scoped.forEach(
        x =>
            itemFilterTypes(x).forEach(type => {
                if (!scopedByType.has(type)) {
                    scopedByType.set(
                        type,
                        new Map()
                    );
                }

                scopedByType
                    .get(type)
                    .set(itemId(x), x);
            })
    );

    const groups =
        displayGroups
            .map(group => {
                const visibleTypes =
                    group.types.filter(
                        type =>
                            (
                                scopedByType
                                    .get(type.id)
                                    ?.size || 0
                            ) > 0
                    );

                if (!visibleTypes.length) {
                    return "";
                }

                const checked =
                    visibleTypes.filter(
                        type =>
                            selectedTypes.has(
                                type.id
                            )
                    ).length;

                const types =
                    visibleTypes
                        .map(type => {
                            const items = [
                                ...(
                                    scopedByType
                                        .get(type.id)
                                        ?.values() ||
                                    []
                                )
                            ],
                                trackable =
                                    items.filter(
                                        item =>
                                            !item.informational
                                    ),
                                done =
                                    trackable.filter(
                                        combinedDone
                                    ).length,
                                progress =
                                    trackable.length
                                        ? `${done.toLocaleString("en-US")}/${trackable.length.toLocaleString("en-US")}`
                                        : `${items.length.toLocaleString("en-US")} pts`,
                                hint =
                                    trackable.length
                                        ? `${done} completed of ${trackable.length}`
                                        : `${items.length} informational point${items.length > 1 ? "s" : ""} - no completion status`;

                            return `<label class="filterType ${selectedTypes.has(type.id) ? "selected" : ""}" title="${esc(hint)}"><input type="checkbox" data-filter-type="${esc(type.id)}" ${selectedTypes.has(type.id) ? "checked" : ""}><span>${esc(type.label)}</span><small class="filterProgress ${trackable.length ? "" : "informational"}">${progress}</small></label>`
                        })
                        .join("");

                return `<details class="filterGroup" open><summary><span>${esc(group.label)}</span><small title="Active filters">${checked}/${visibleTypes.length} filters</small></summary><div>${types}</div></details>`;
            })
            .join("");

    $("#categories").innerHTML =
        `<div class="filterHeading"><b>Map Filters</b><span><button data-filter-action="all">All</button><button data-filter-action="none">None</button></span></div>${groups}`;

    document
        .querySelectorAll(
            "[data-filter-type]"
        )
        .forEach(
            input =>
                input.onchange = () => {
                    input.checked
                        ? selectedTypes.add(
                            input.dataset.filterType
                        )
                        : selectedTypes.delete(
                            input.dataset.filterType
                        );

                    listRenderLimit =
                        LIST_PAGE_SIZE;

                    renderFilterNav();
                    renderItems();
                }
        );

    document
        .querySelectorAll(
            "[data-filter-action]"
        )
        .forEach(
            button =>
                button.onclick = () => {
                    if (
                        button.dataset
                            .filterAction === "all"
                    ) {
                        available.forEach(
                            type =>
                                selectedTypes.add(type)
                        );
                    } else {
                        selectedTypes.clear();
                    }

                    listRenderLimit =
                        LIST_PAGE_SIZE;

                    renderFilterNav();
                    renderItems();
                }
        );
}

function filtered() {
    const q =
        $("#search").value.toLowerCase(),
        status = $("#status").value,
        dlc = $("#dlc").value,
        region = $("#region").value,
        variant = $("#variant").value;

    return allItems().filter(
        x =>
            selectedTypeMatches(x) &&
            gameModeMatches(x) &&
            locationMatches(x) &&

            (
                status === "all" ||

                (
                    status === "done"
                        ? combinedDone(x) &&
                            !x.informational

                        : status === "automatic"
                            ? x.termine

                            : status === "manual"
                                ? manualDone(x)

                                : status === "mixed"
                                    ? trackingMode(x) === "mixed"

                                    : status === "info"
                                        ? x.informational

                                        : x.informational ||
                                            !combinedDone(x)
                )
            ) &&

            originMatches(x, dlc) &&

            (
                region === "all" ||
                x.region === region
            ) &&

            (
                variant === "all" ||
                x.subtype === variant
            ) &&

            (
                !q ||

                [
                    x.name,
                    x.subtype,
                    x.acteur,
                    x.content_origin_label,
                    x.region,
                    x.nearby,
                    x.trial,
                    x.quest,
                    x.display_location,
                    x.section,

                    ...(x.geo_points || [])
                        .flatMap(
                            p => [
                                p.label,
                                p.nearby
                            ]
                        )
                ].some(
                    v =>
                        String(v || "")
                            .toLowerCase()
                            .includes(q)
                )
            )
    );
}

function armorLine(x) {
    if (
        ![
            "armures",
            "armures_max"
        ].includes(x.categorie)
    ) {
        return "";
    }

    const next =
        x.prochaine_amelioration;

    const ready =
        next?.possible
            ? "  =  materials ready"
            : "";

    return `${x.etoiles || "☆☆☆☆"}${
        x.possede
            ? ` • Level ${x.niveau}/4`
            : "  =  not possessed"
    }${ready}`;
}

function renderItems() {
    refreshVariants();

    const items = filtered();

    $("#resultCount").textContent =
        `${items.length} result${items.length > 1 ? "s" : ""}`;

    $("#mapCount").textContent =
        `${items.filter(x => x.x != null && x.z != null).length} with coordinates`;

    renderFilterScopeNotice(items);

    const labels = [
        ...new Set(
            items
                .map(x => x.filter_label)
                .filter(Boolean)
        )
    ];

    $("#listTitle").textContent =
        labels.length === 1
            ? labels[0]
            : "Filtered elements";

    const planned = routeIds();

    const visibleItems =
        items.slice(
            0,
            listRenderLimit
        ),
        more =
            items.length -
            visibleItems.length;

    $("#list").innerHTML =
        items.length
            ? visibleItems
                .map(
                    x =>
                        `<div class="item" data-id="${esc(itemId(x))}"><button type="button" class="itemOpen" data-item-open="${esc(itemId(x))}"><i class="dot ${stateClass(x)}" aria-hidden="true"></i><span class="itemText"><strong>${esc(x.name || x.display_name || x.id)}</strong><span class="trackingBadge ${trackingMode(x)}">${esc(trackingLabel(x))}</span><span class="itemMeta">${esc([
                            armorLine(x),
                            x.subtype,
                            x.region,
                            x.nearby
                                ? `near ${x.nearby}`
                                : null,
                            x.trial,
                            x.quest,
                            x.section,
                            x.statut,
                            x.mode_expert
                                ? "mode expert"
                                : null,
                            x.content_origin !== "base"
                                ? x.content_origin_label
                                : null
                        ].filter(Boolean).join(" • "))}</span>${x.raison ? `<span class="itemMeta">${esc(x.raison)}</span>` : ""}</span><span class="coords">${x.x != null ? `X ${x.x.toFixed(0)} · Z ${x.z.toFixed(0)}` : ""}</span></button>${x.x != null ? `<button type="button" class="routeAdd ${planned.has(itemId(x)) ? "active" : ""}" data-route-add="${esc(itemId(x))}" aria-label="${planned.has(itemId(x)) ? "Remove" : "Add"} ${esc(x.name || x.display_name || x.id)} ${planned.has(itemId(x)) ? "of" : "at"} the route" title="${planned.has(itemId(x)) ? "Remove from" : "Add to"} the route">${planned.has(itemId(x)) ? "✓" : "+"}</button>` : ""}</div>`
                )
                .join("") +

                (
                    more
                        ? `<button id="showMoreResults" class="showMoreResults">Show ${Math.min(LIST_PAGE_SIZE, more)} more results • ${more.toLocaleString("en-US")} remaining</button>`
                        : ""
                )
            : "<div class=\"empty\">No items with these filters.</div>";

    renderMap(items);

    document
        .querySelectorAll(
            "#list [data-item-open]"
        )
        .forEach(
            el =>
                el.onclick =
                    () =>
                        select(
                            el.dataset.itemOpen,
                            true
                        )
        );

    document
        .querySelectorAll(
            "#list [data-route-add]"
        )
        .forEach(
            button =>
                button.onclick =
                    event => {
                        event.stopPropagation();

                        toggleRouteItem(
                            button.dataset.routeAdd
                        );
                    }
        );

    if ($("#showMoreResults")) {
        $("#showMoreResults").onclick =
            () => {
                listRenderLimit +=
                    LIST_PAGE_SIZE;

                renderItems();
            };
    }
}

function renderFilterScopeNotice(items) {
    const audit =
        report.filter_scope_audit || {},
        mode = selectedGameMode(),
        saveMode =
            report.sauvegarde.mode === "expert"
                ? "expert"
                : "normal";

    const expert =
        items.filter(
            x =>
                x.game_mode_scope ===
                "expert_only"
        ).length;

    const map =
        items.filter(
            x =>
                x.display_scope ===
                "map_and_list"
        ).length,
        interior =
            items.filter(
                x =>
                    x.display_scope ===
                    "interior_only"
            ).length,
        list =
            items.filter(
                x =>
                    x.display_scope ===
                    "list_only"
            ).length;

    const warning =
        mode === "all" &&
        saveMode === "normal"
            ? `All modes are displayed: ${expert.toLocaleString("en-US")} placement${expert > 1 ? "s" : ""} exclusive to Master Mode included.`
            : mode === "normal"
                ? "Placements exclusive to Master Mode are hidden."
                : mode === "expert"
                    ? "Common placements and placements exclusive to Master Mode are displayed."
                    : "";

    $("#filterScopeNotice").innerHTML =
        `<b>Verified coverage</b><span>${esc(warning)} ${map.toLocaleString("en-US")} on Hyrule • ${interior.toLocaleString("en-US")} on interior maps • ${list.toLocaleString("en-US")} in the list only.</span>${audit.status && audit.status !== "complete" ? "<strong>The reference counters require verification.</strong>" : ""}`;
}

async function select(id, fromList = false) {
    detailReturnTarget = {
        id,
        fromList,
        manualReview: !$("#manualReview").hidden
    };
    selectedId = id;
    renderItems();

    const item =
        allItems().find(
            x => itemId(x) === id
        );

    if (!item) {
        return;
    }

    if (
        item.x != null &&
        item.z != null
    ) {
        focusItem(
            item,
            fromList
                ? Math.max(
                    mapState.scale,
                    mapState.minScale * 2.2
                )
                : mapState.scale
        );
    }

    const drawer = $("#itemDetails");

    drawer.classList.add("open");
    drawer.inert = false;

    drawer.setAttribute(
        "aria-hidden",
        "false"
    );

    $("#closeDetails").focus();

    $("#detailContent").innerHTML =
        "<div class=\"detailLoading\"><b id=\"detailTitle\">Loading details…</b><small>Details are retrieved locally on request.</small></div>";

    try {
        let detailed =
            detailCache.get(id);

        if (!detailed) {
            const response =
                await fetch(
                    `/api/detail/${encodeURIComponent(id)}`
                ),
                payload =
                    await response.json();

            if (!response.ok) {
                throw Error(
                    payload.erreur ||
                    "Details unavailable"
                );
            }

            if (
                payload.report_revision_key !==
                report.report_revision_key
            ) {
                throw Error(
                    "This sheet belongs to another revision of the save"
                );
            }

            detailed =
                payload.item;

            detailCache.set(
                id,
                detailed
            );
        }

        if (selectedId !== id) {
            return;
        }

        Object.assign(
            item,
            detailed
        );

        renderDetails(item);
        renderMap(filtered());

    } catch (error) {
        if (selectedId === id) {
            $("#detailContent").innerHTML =
                `<div class="empty">${esc(error.message)}</div>`;
        }

        toast(
            error.message,
            true
        );
    }

    const row =
        [...document.querySelectorAll(".item")]
            .find(
                x =>
                    x.dataset.id === id
            );

    if (row && !fromList) {
        const list = $("#list");

        if (list) {
            const listRect = list.getBoundingClientRect();
            const rowRect = row.getBoundingClientRect();

            if (rowRect.top < listRect.top) {
                list.scrollTo({
                    top:
                        list.scrollTop +
                        rowRect.top -
                        listRect.top,
                    behavior: "smooth"
                });
            } else if (rowRect.bottom > listRect.bottom) {
                list.scrollTo({
                    top:
                        list.scrollTop +
                        rowRect.bottom -
                        listRect.bottom,
                    behavior: "smooth"
                });
            }
        }
    }
}

function mapRect() {
    return $("#map").getBoundingClientRect()
}

function clampMap() {
    const r = mapRect(),
        w = MAP_W * mapState.scale,
        h = MAP_H * mapState.scale;

    mapState.x =
        w <= r.width
            ? (r.width - w) / 2
            : Math.min(
                0,
                Math.max(
                    r.width - w,
                    mapState.x
                )
            );

    mapState.y =
        h <= r.height
            ? (r.height - h) / 2
            : Math.min(
                0,
                Math.max(
                    r.height - h,
                    mapState.y
                )
            );
}

function applyMap() {
    clampMap();

    const pixelRatio = window.devicePixelRatio || 1,
        renderX = Math.round(mapState.x * pixelRatio) / pixelRatio,
        renderY = Math.round(mapState.y * pixelRatio) / pixelRatio;

    $("#mapStage").style.transform =
        `translate(${renderX}px,${renderY}px) scale(${mapState.scale})`;

    $("#mapStage").style.setProperty(
        "--pin-scale",
        1 / mapState.scale
    );

    renderMapTiles();
}

function clearMapTiles() {
    mapTileNodes.forEach(node => node.remove());
    mapTileNodes.clear();
}

function renderMapTiles() {
    const host = $("#mapTiles");

    if (!host || !mapState.ready) {
        return
    }

    const requiredDensity = mapState.scale * Math.min(2, window.devicePixelRatio || 1),
        level = requiredDensity <= 3
            ? null
            : MAP_TILE_LEVELS.find(candidate => candidate.density >= requiredDensity)
                || MAP_TILE_LEVELS.at(-1);

    if (!level) {
        activeMapTileLevel = null;
        clearMapTiles();
        return
    }

    if (activeMapTileLevel !== level.id) {
        activeMapTileLevel = level.id;
        clearMapTiles();
    }

    const rect = mapRect(),
        margin = 96 / mapState.scale,
        left = Math.max(0, (-mapState.x / mapState.scale) - margin),
        top = Math.max(0, (-mapState.y / mapState.scale) - margin),
        right = Math.min(MAP_W, ((rect.width - mapState.x) / mapState.scale) + margin),
        bottom = Math.min(MAP_H, ((rect.height - mapState.y) / mapState.scale) + margin);

    if (right <= left || bottom <= top) {
        clearMapTiles();
        return
    }

    const columns = Math.ceil(level.width / MAP_TILE_SIZE),
        rows = Math.ceil(level.height / MAP_TILE_SIZE),
        firstColumn = Math.max(0, Math.floor(left * level.density / MAP_TILE_SIZE)),
        lastColumn = Math.min(columns - 1, Math.floor((right * level.density - 1) / MAP_TILE_SIZE)),
        firstRow = Math.max(0, Math.floor(top * level.density / MAP_TILE_SIZE)),
        lastRow = Math.min(rows - 1, Math.floor((bottom * level.density - 1) / MAP_TILE_SIZE)),
        required = new Set();

    for (let row = firstRow; row <= lastRow; row += 1) {
        for (let column = firstColumn; column <= lastColumn; column += 1) {
            const key = `${level.id}:${column}:${row}`;
            required.add(key);

            if (mapTileNodes.has(key)) {
                continue
            }

            const sourceX = column * MAP_TILE_SIZE,
                sourceY = row * MAP_TILE_SIZE,
                sourceWidth = Math.min(MAP_TILE_SIZE, level.width - sourceX),
                sourceHeight = Math.min(MAP_TILE_SIZE, level.height - sourceY),
                tile = document.createElement("img");

            tile.className = "mapTile";
            tile.alt = "";
            tile.draggable = false;
            tile.decoding = "async";
            tile.addEventListener("error", () => {
                tile.remove();
                if (mapTileNodes.get(key) === tile) {
                    mapTileNodes.delete(key);
                }
            }, { once: true });
            tile.src = `/map-tiles/${level.id}/${column}_${row}.webp`;
            tile.style.left = `${sourceX / level.density}px`;
            tile.style.top = `${sourceY / level.density}px`;
            // A two-source-pixel overlap prevents Safari from exposing the
            // background between images transformed onto subpixels.
            tile.style.width = `${sourceWidth / level.density + 2 / level.density}px`;
            tile.style.height = `${sourceHeight / level.density + 2 / level.density}px`;
            host.appendChild(tile);
            mapTileNodes.set(key, tile);
        }
    }

    mapTileNodes.forEach((node, key) => {
        if (!required.has(key)) {
            node.remove();
            mapTileNodes.delete(key);
        }
    });
}

function resetMap() {
    const r = mapRect();

    mapState.minScale =
        Math.min(
            r.width / MAP_W,
            r.height / MAP_H
        );

    mapState.scale =
        mapState.minScale;

    mapState.x = 0;
    mapState.y = 0;
    mapState.ready = true;

    applyMap();

    if (report) {
        renderMap(filtered());
    }
}

function zoomMap(next, px, py) {
    const r = mapRect(),
        cx = px ?? r.width / 2,
        cy = py ?? r.height / 2,
        old = mapState.scale;

    next =
        Math.min(
            mapState.minScale * 9,
            Math.max(
                mapState.minScale,
                next
            )
        );

    const wx =
        (cx - mapState.x) / old,
        wy =
            (cy - mapState.y) / old;

    mapState.scale = next;
    mapState.x = cx - wx * next;
    mapState.y = cy - wy * next;

    applyMap();
    renderMap(filtered());
}

function focusWorld(p, scale) {
    const r = mapRect();

    mapState.scale =
        Math.min(
            mapState.minScale * 9,
            Math.max(
                mapState.minScale,
                scale
            )
        );

    mapState.x =
        r.width / 2 -
        p.x * mapState.scale;

    mapState.y =
        r.height / 2 -
        p.y * mapState.scale;

    applyMap();
    renderMap(filtered());
}

function focusItem(item, scale) {
    focusWorld(
        worldPoint(item),
        scale
    )
}

function renderMap(items) {
    if (!mapState.ready) {
        return;
    }

    let located =
        items.filter(
            x =>
                x.x != null &&
                x.z != null &&
                Math.abs(x.x) <= 6000 &&
                Math.abs(x.z) <= 5000
        );

    const ratio =
        mapState.scale /
        mapState.minScale,
        cluster =
            located.length > 180 &&
            ratio < 3;

    if (
        !cluster &&
        located.length > 500
    ) {
        const rect = mapRect(),
            margin =
                80 / mapState.scale,
            minX =
                (-mapState.x - margin) /
                mapState.scale,
            maxX =
                (
                    rect.width -
                    mapState.x +
                    margin
                ) /
                mapState.scale,
            minY =
                (-mapState.y - margin) /
                mapState.scale,
            maxY =
                (
                    rect.height -
                    mapState.y +
                    margin
                ) /
                mapState.scale;

        located =
            located.filter(item => {
                const p =
                    worldPoint(item);

                return (
                    p.x >= minX &&
                    p.x <= maxX &&
                    p.y >= minY &&
                    p.y <= maxY
                )
            });
    }

    let groups = [];

    if (cluster) {
        const cell =
            52 / mapState.scale,
            buckets = new Map();

        located.forEach(item => {
            const p =
                worldPoint(item),
                key =
                    `${Math.floor(p.x / cell)}:${Math.floor(p.y / cell)}`;

            if (!buckets.has(key)) {
                buckets.set(
                    key,
                    []
                );
            }

            buckets
                .get(key)
                .push(item);
        });

        groups =
            [...buckets.values()];

    } else {
        groups =
            located.map(x => [x]);
    }

    const baseMarkers =
        groups.map(group => {
            if (group.length === 1) {
                const x = group[0],
                    p = worldPoint(x),
                    id = itemId(x);

                // Dense points remain clickable with a mouse. Their keyboard
                // equivalent is the full row in the filtered list, which also
                // avoids hundreds of redundant Tab stops.
                return `<span aria-hidden="true" title="${esc(x.name)}" data-map-id="${esc(id)}" class="marker baseMapMarker ${stateClass(x)} ${selectedId === id ? "selected" : ""}" style="left:${p.x / MAP_W * 100}%;top:${p.y / MAP_H * 100}%"></span>`
            }

            const points =
                group.map(worldPoint),
                p = {
                    x:
                        points.reduce(
                            (a, v) =>
                                a + v.x,
                            0
                        ) /
                        points.length,
                    y:
                        points.reduce(
                            (a, v) =>
                                a + v.y,
                            0
                        ) /
                        points.length
                };

            return `<button type="button" title="Zoom to ${group.length} items" aria-label="Zoom to ${group.length} items" data-cluster-x="${p.x}" data-cluster-y="${p.y}" class="marker cluster" style="left:${p.x / MAP_W * 100}%;top:${p.y / MAP_H * 100}%">${group.length}</button>`;
        }).join("");

    const selected =
        allItems().find(
            x =>
                itemId(x) === selectedId
        );

    const route =
        (selected?.geo_points || [])
            .filter(
                p =>
                    p.x != null &&
                    p.z != null &&
                    Math.abs(p.x) <= 6000 &&
                    Math.abs(p.z) <= 5000
            );

    const routeMarkers =
        route.map(
            (point, index) => {
                const p =
                    worldPoint(point);

                return `<button type="button" title="${esc(point.label)}" aria-label="Step ${index + 1} : ${esc(point.label)}" data-route-index="${index}" class="marker waypoint" style="left:${p.x / MAP_W * 100}%;top:${p.y / MAP_H * 100}%">${index + 1}</button>`
            }
        ).join("");

    const planned =
        routePoints(),
        start =
            routeState.start;

    const plannerMarkers =
        planned.map(
            (point, index) => {
                const p =
                    worldPoint(point);

                return `<button type="button" title="Step ${index + 1} - ${esc(point.name)}" aria-label="Planned step ${index + 1}: ${esc(point.name)}" data-planner-index="${index}" class="marker plannerWaypoint ${point.locked ? "locked" : ""}" style="left:${p.x / MAP_W * 100}%;top:${p.y / MAP_H * 100}%">${index + 1}</button>`
            }
        ).join("");

    const startMarker =
        start
            ? (() => {
                const p =
                    worldPoint(start);

                return `<button type="button" title="Start - ${esc(start.label || "Custom Point")}" aria-label="Starting point: ${esc(start.label || "Custom Point")}" class="marker routeStart" style="left:${p.x / MAP_W * 100}%;top:${p.y / MAP_H * 100}%">D</button>`
            })()
            : "";

    $("#markers").innerHTML =
        baseMarkers +
        routeMarkers +
        plannerMarkers +
        startMarker;

    const pathPoints =
        route
            .map(worldPoint)
            .map(
                p => `${p.x},${p.y}`
            )
            .join(" ");

    const plannerPath =
        [
            ...(start ? [start] : []),
            ...planned
        ]
            .map(worldPoint)
            .map(
                p => `${p.x},${p.y}`
            )
            .join(" ");

    $("#geoPath").innerHTML =
        (
            route.length > 1
                ? `<polyline class="detailPath" points="${pathPoints}"></polyline>`
                : ""
        ) +
        (
            planned.length > 1 ||
            start && planned.length
                ? `<polyline class="plannerPath" points="${plannerPath}"></polyline>`
                : ""
        );

    document
        .querySelectorAll(
            "[data-map-id]"
        )
        .forEach(
            el =>
                el.onclick =
                    e => {
                        e.stopPropagation();

                        select(
                            el.dataset.mapId
                        );
                    }
        );

    document
        .querySelectorAll(
            "[data-cluster-x]"
        )
        .forEach(
            el =>
                el.onclick =
                    e => {
                        e.stopPropagation();

                        focusWorld(
                            {
                                x:
                                    +el.dataset.clusterX,
                                y:
                                    +el.dataset.clusterY
                            },
                            mapState.scale * 2.35
                        );
                    }
        );

    document
        .querySelectorAll(
            "[data-route-index]"
        )
        .forEach(
            el =>
                el.onclick =
                    e => {
                        e.stopPropagation();

                        focusWorld(
                            worldPoint(
                                route[
                                    +el.dataset.routeIndex
                                ]
                            ),
                            Math.max(
                                mapState.scale,
                                mapState.minScale * 3
                            )
                        );
                    }
        );

    document
        .querySelectorAll(
            "[data-planner-index]"
        )
        .forEach(
            el =>
                el.onclick =
                    e => {
                        e.stopPropagation();

                        const point =
                            planned[
                                +el.dataset.plannerIndex
                            ];

                        select(
                            itemId(point)
                        );

                        focusItem(
                            point,
                            Math.max(
                                mapState.scale,
                                mapState.minScale * 3
                            )
                        );
                    }
        );

    applyMap();
}

function helpFor(x) {
    const coord =
        x.x != null
            ? `The marker is placed at coordinates X ${x.x.toFixed(1)}, Z ${x.z.toFixed(1)}.`
            : "This objective does not yet have reliable coordinates in the local database.";

    if (x.farm) {
        return `${coord} This farm point is always displayed: the enemy reappears after a blood moon, even if a previous victory is recorded. ${x.scalable ? "Its family and location are reliable, but its variant may have changed with world difficulty." : "The static variant shown comes from the game placement data."}`;
    }

    const guide = {
        sanctuaires:
            `${coord} Activate the travel point, complete the trial${x.trial ? ` « ${x.trial} »` : ""} and examine the altar. Remember the optional chest before leaving.${x.quest ? ` Access depends on the quest “${x.quest}”.` : ""}`,

        coffres_sanctuaires:
            `${coord} Return to this shrine and check every room before the altar. ${x.raison || "The chest is not marked as opened in the save."}`,

        coffres_monde:
            `${coord} This chest has a permanent flag: opening it will be detected in your next save.${x.contenu ? ` Identified Content: ${x.contenu}.` : ""}`,

        coffres_donjons:
            `Explore the ${x.secteur || "the Dungeon"} area before leaving. This chest has a permanent flag and will be marked as completed after you save.`,

        korogus:
            `${coord} Look for a small environmental puzzle near the point: stones, a circle, flowers, a pinwheel, a balloon, a stump or an offering. The save does not store the exact puzzle type.`,

        tours:
            `${coord} Reach the top and examine the Sheikah terminal. The next save will automatically validate the tower.`,

        lieux:
            `${coord} Walk through this area until its name appears on screen. Being nearby or flying over it may not trigger the flag.`,

        quetes_sanctuaires:
            `${coord} This first marker is the start of the quest. The destination ${x.sanctuaire ? `« ${x.sanctuaire} »` : "the Shrine"} is listed separately below, with possible intermediate objectives.`,

        quetes_principales:
            `${coord} Start at the first marker, then check the objectives below. The Companion checks the official completion flag, not just whether the quest has started.`,

        quetes_secondaires:
            `${coord} The first marker shows where to start or, for the Xenoblade crossover, the first clue. Current status: “${x.statut}”${x.region ? ` in the region ${x.region}` : ""}.`,

        souvenirs:
            `${coord} Reach the marker and then trigger the scene. A simple visit to the place is not enough: the cinematic must have been recorded.`,

        hinox:
            `${coord} Defeat this Hinox, then save your game. Its individual flag is used for Kilton’s Medal of Honor.`,

        talus:
            `${coord} Defeat this Stone Talus, then save your game. Attack the ore deposit on its body to deal damage.`,

        moldarquors:
            `${coord} Lure the Molduga with a bomb on the ground, detonate it when it leaps, then attack it and save your game.`,

        compendium:
            `Photograph ${x.name} with the Camera rune until it is identified, or buy its picture at the Hateno Ancient Tech Lab when that option is available.`,

        armures:
            `Obtain ${x.name} at least once. Ownership and its actual level (${x.etoiles || "☆☆☆☆"}) are read directly from the save inventory.`,

        armures_max:
            x.possede
                ? `Upgrade ${x.name} at a Great Fairy Fountain to level 4. Current detected level: ${x.niveau}/4 (${x.etoiles}).`
                : `First obtain ${x.name}, then upgrade it four times at Great Fairy Fountains.`,
    };

    return guide[x.categorie] || coord;
}

function guideList(
    title,
    items,
    ordered = false,
    kind = ""
) {
    if (!items?.length) {
        return "";
    }

    const tag =
        ordered ? "ol" : "ul";

    return `<div class="guideDetail ${esc(kind)}"><b>${esc(title)}</b><${tag}>${items.map(item => `<li>${esc(item)}</li>`).join("")}</${tag}></div>`;
}

function frenchSourceName(name, itemName) {
    if (name.startsWith("Zelda Wiki - ")) {
        return `Zelda Wiki - article about “${itemName}”`;
    }

    const exact = {
        "BOTW Event Flow Viewer - flux de quête":
            "Viewer of BOTW event flows",
        "BOTW Object Map":
            "Map of BOTW objects (ObjMap)",
        "Zelda Dungeon Interactive Map":
            "Zelda Dungeon - interactive map",
        "Zelda Dungeon - Leviathan Bones":
            "Zelda Dungeon - article on whale fossils",
        "Zelda Dungeon - Sunken Treasure":
            "Zelda Dungeon - article on the sunken treasures",
        "Zelda Dungeon - Épreuves de l'Épée":
            "Zelda Dungeon - Trials of the Sword"
    };

    return exact[name] || name;
}

function guideSources(sources, itemName) {
    if (!sources?.length) {
        return "";
    }

    return `<div class="guideSources"><small>REFERENCE SOURCES</small>${sources.map(source => `<a href="${esc(source.url)}" target="_blank" rel="noreferrer">${esc(frenchSourceName(source.name, itemName))} ↗</a>`).join("")}</div>`;
}

function renderDetails(x) {
    const category =
        report.categories[x.categorie]?.label ||
        x.filter_label ||
        "Map information";

    const displayLabels = {
        map_and_list:
            "Hyrule map and list",
        interior_only:
            "Internal map and list",
        list_only:
            "List only"
    };

    const facts = [
        ["Region", x.region],
        ["Origin", x.content_origin_label],
        ["Position", x.placement_label],
        ["Coverage", x.coverage_label],
        ["Display", displayLabels[x.display_scope]],
        ["Location", x.location_status_label],
        ["Mode", x.game_mode_label],
        ["Activity", x.activity_scope_label],
        ["Initial variant", x.subtype],
        ["Reward", x.reward],
        [
            "Farm blood moon",
            x.farm
                ? "Always displayed"
                : null
        ],
        [
            "Developments",
            x.scalable
                ? "Variant that may change"
                : null
        ],
        ["Nearby location", x.nearby],
        ["Test", x.trial],
        ["Linked Quest", x.quest],
        ["Shrine", x.sanctuaire],
        ["Contents", x.contenu],
        ["Sector", x.secteur || x.section],
        ["Set", x.set],
        [
            "Level",
            x.niveau != null
                ? `${x.niveau}/4 ${x.etoiles}`
                : null
        ]
    ].filter(v => v[1] != null);

    const coords =
        x.x != null &&
        x.z != null;

    const objmap =
        coords
            ? `https://objmap.zeldamods.org/#/map/z6,${x.x},${x.z}`
            : "";

    const search =
        `https://www.google.com/search?q=${encodeURIComponent(`Zelda BOTW ${x.name} guide`)}`;

    const upgrade =
        x.prochaine_amelioration;

    const recipe =
        upgrade
            ? `<div class="detailSection"><h3>Materials to reach ${"★".repeat(upgrade.niveau_cible)}</h3><div class="recipe">${upgrade.materiaux.map(m => `<div class="recipeRow ${m.disponible ? "ready" : "missing"}"><span>${esc(m.name)}</span><b>${m.possede} / ${m.requis}</b><small>${m.manque ? `missing ${m.manque}` : "ready"}</small></div>`).join("")}</div></div>`
            : "";

    const geo =
        x.geo_points || [];

    const geoBlock =
        geo.length
            ? `<div class="detailSection"><h3>${geo.length > 1 ? "Steps and Locations" : "Location"}</h3><div class="geoPoints">${geo.map((p, i) => `<article class="geoPoint"><div><b>${esc(p.label)}</b><small>${esc(p.nearby ? `Near ${p.nearby}${p.nearby_distance_m != null ? ` • approximately ${p.nearby_distance_m} m` : ""}` : "World coordinates")}</small><span>X ${Number(p.x).toFixed(2)} • Z ${Number(p.z).toFixed(2)}</span></div><div class="geoActions"><button data-geo-center="${i}">Map</button><button data-geo-copy="${i}">Copy</button><a href="https://objmap.zeldamods.org/#/map/z6,${p.x},${p.z}" target="_blank" rel="noreferrer">ObjMap ↗</a></div></article>`).join("")}</div></div>`
            : "";

    const guide = x.guide;

    const interiorPoints =
        x.interior_chests ||
        (
            x.interior_position
                ? [x.interior_position]
                : []
        );

    const interiorBlock =
        interiorPoints.length
            ? `<div class="detailSection interiorCard"><h3>${esc(x.interior_map_label || "Interior map")}</h3><p>${interiorPoints.length} physical chest${interiorPoints.length > 1 ? "s" : ""} recorded in the game data.</p><div class="interiorPoints">${interiorPoints.map((p, i) => { const detail = guide?.chest_details?.[i] || p; return `<article><span>${detail.number || i + 1}</span><div><b>${esc(p.content || x.contenu || "Treasure Chest")}</b>${detail.area ? `<small>${esc(detail.area)}</small>` : `<small>X ${Number(p.x).toFixed(2)} • Y ${Number(p.y).toFixed(2)} • Z ${Number(p.z).toFixed(2)}</small>`}${detail.access_label ? `<em>${esc(detail.access_label)}</em>` : ""}${detail.access ? `<p>${esc(detail.access)}</p>` : ""}</div></article>`; }).join("")}</div><small class="interiorNote">These coordinates belong to ${esc(x.interior_map)}: they are intentionally kept separate from the Hyrule map.</small></div>`
            : "";

    const stateLabels = {
        termine: "Completed",
        actuel: "Current stage",
        a_faire: "To do",
        a_verifier: "To be checked",
        verrouille: "After activation"
    };

    const qualityBlock =
        guide?.quality_label
            ? `<div class="guideQuality quality${guide.quality_level}"><b>${esc(guide.quality_label)}</b><small>${esc(guide.verification_basis)}</small></div>`
            : "";

    const evidenceBlock =
        guide?.quest_evidence
            ? `<div class="guideEvidence"><small>PROOF OF THE QUEST FLOW</small><p>${guide.quest_evidence.event_nodes} nodes • ${guide.quest_evidence.event_actions} actions • ${guide.quest_evidence.message_references} dialogue references</p></div>`
            : "";

    const trialBlock =
        guide?.trial_rooms?.length
            ? `<div class="trialRooms"><h3>Rooms at this level</h3>${guide.trial_rooms.map(room => `<article class="trialRoom ${esc(room.kind)}"><span>${room.floor}</span><div><small>${esc(room.kind_label)}</small><b>${esc(room.enemies)}</b><p>${esc(room.strategy)}</p></div></article>`).join("")}</div>`
            : "";

    const bossBlock =
        guide?.boss_profile
            ? `<div class="guideBoss"><small>COMBAT PROFILE</small><b>${esc(guide.boss_profile.variant)}</b><p><strong>Weak point:</strong> ${esc(guide.boss_profile.weak_point)}</p>${guide.boss_profile.scaling ? `<p>${esc(guide.boss_profile.scaling)}</p>` : ""}</div>`
            : "";

    const guideBlock =
        guide
            ? `<div class="detailSection guideCard"><div class="guideTitle"><h3>Objective guide</h3>${guide.specificity_label ? `<span>${esc(guide.specificity_label)}</span>` : ""}</div>${qualityBlock}<p class="guideSummary">${esc(guide.summary)}</p>${guide.mechanic ? `<div class="guideMechanic"><small>MECHANIC</small><b>${esc(guide.mechanic)}</b></div>` : ""}${bossBlock}<div class="currentAction"><small>NEXT ACTION</small><b>${esc(guide.current_action)}</b></div>${guideList("Prerequisite", guide.prerequisites)}${guideList("Preparation", guide.preparation)}${evidenceBlock}${trialBlock}${guide?.trial_rooms?.length ? "" : guideList("Detailed solution", guide.detailed_steps, true, "solution")}${guide.chest_solution ? `<div class="guideChest"><small>SHRINE CHEST</small><p>${esc(guide.chest_solution)}</p></div>` : ""}${guideList("Rewards", guide.rewards, false, "rewards")}<div class="guideSteps">${(guide.steps || []).map((s, i) => `<article class="guideStep ${esc(s.state)}"><span>${i + 1}</span><div><b>${esc(s.title)}</b><p>${esc(s.instruction)}</p><small>${esc(stateLabels[s.state] || s.state)}</small></div>${s.geo_point_index != null && geo[s.geo_point_index] ? `<button data-guide-center="${s.geo_point_index}">Map</button>` : ""}</article>`).join("")}</div>${guideList("Tips", guide.tips, false, "tips")}${guideList("Notes", guide.warnings, false, "warnings")}<div class="completionProof"><small>${guide.completion.automatic === false ? "TRACKING" : "AUTOMATIC COMPLETION"}</small><p>${esc(guide.completion.condition)}</p></div>${guideSources(guide.sources, x.name || "this objective")}</div>`
            : `<div class="detailSection"><h3>How to finish it</h3><p>${esc(helpFor(x))}</p></div>`;

    const manual =
        manualEntry(x),
        farmWarning =
            x.farm
                ? "This state never removes this farm point from its category: the enemy reappears at the blood moon."
                : "The validation remains after a new analysis of the save.";

    const scopeBlock =
        x.coverage_note
            ? `<div class="detailSection scopeWarning"><h3>Limit of coverage</h3><p>${esc(x.coverage_note)}</p></div>`
            : "";

    const manualBlock =
        `<div class="detailSection manualTracking"><h3>Persistent manual tracking</h3><div class="statusSplit"><span><small>Save</small><b>${x.termine ? "Validated automatically" : "Not automatically validated"}</b></span><span><small>Personal</small><b>${manual.completed ? "Validated manually" : "Not checked"}</b></span></div><label class="manualCheck"><input id="manualComplete" type="checkbox" ${manual.completed ? "checked" : ""}><span>Mark this objective as manually completed</span></label><label class="manualNoteLabel">Personal note<textarea id="manualNoteInput" maxlength="1000" placeholder="Optional: personal best, checked chest, next action…">${esc(manual.note || "")}</textarea></label><button id="saveManualNote">Save note</button><p class="manualHint">${esc(farmWarning)}</p></div>`;

    const inRoute =
        routeIds().has(itemId(x));

    $("#detailContent").innerHTML =
        `<p class="detailEyebrow">${esc(category)}</p><h2 id="detailTitle">${esc(x.name || x.id)}</h2><p class="detailMeta">${esc([x.region, x.dlc ? "DLC" : null].filter(Boolean).join(" • "))}</p><span class="detailStatus"><i class="dot ${stateClass(x)}" aria-hidden="true"></i>${esc(trackingLabel(x))}</span>${facts.length ? `<div class="detailFacts">${facts.map(([k, v]) => `<div class="detailFact"><small>${esc(k)}</small>${esc(v)}</div>`).join("")}</div>` : ""}${scopeBlock}${manualBlock}${guideBlock}${geoBlock}${interiorBlock}${recipe}${coords && !geo.length ? `<div class="detailSection"><h3>BOTW coordinates</h3><p>X ${x.x.toFixed(2)} • Z ${x.z.toFixed(2)}</p></div>` : ""}<div class="detailActions">${coords ? `<button id="detailRoute">${inRoute ? "Remove from" : "Add to"} the route</button><button id="detailCenter">Center on the map</button><button id="copyCoords">Copy the main point</button><a href="${objmap}" target="_blank" rel="noreferrer">ObjMap ↗</a>` : ""}<a href="${search}" target="_blank" rel="noreferrer">Find a guide ↗</a></div>`;

    const drawer =
        $("#itemDetails");

    drawer.classList.add("open");

    drawer.setAttribute(
        "aria-hidden",
        "false"
    );

    if (coords) {
        $("#detailRoute").onclick =
            () => {
                toggleRouteItem(itemId(x));
                renderDetails(x);
            };

        $("#detailCenter").onclick =
            () =>
                focusItem(
                    x,
                    Math.max(
                        mapState.scale,
                        mapState.minScale * 3
                    )
                );

        $("#copyCoords").onclick =
            async () => {
                await copyText(
                    `${x.x}, ${x.z}`
                );

                toast(
                    "Coordinates copied"
                );
            };
    }

    document
        .querySelectorAll(
            "[data-geo-center]"
        )
        .forEach(
            button =>
                button.onclick =
                    () => {
                        const p =
                            geo[
                                +button.dataset.geoCenter
                            ];

                        focusWorld(
                            worldPoint(p),
                            Math.max(
                                mapState.scale,
                                mapState.minScale * 3
                            )
                        );
                    }
        );

    document
        .querySelectorAll(
            "[data-geo-copy]"
        )
        .forEach(
            button =>
                button.onclick =
                    async () => {
                        const p =
                            geo[
                                +button.dataset.geoCopy
                            ];

                        await copyText(
                            `${p.x}, ${p.z}`
                        );

                        toast(
                            "Coordinates copied"
                        );
                    }
        );

    document
        .querySelectorAll(
            "[data-guide-center]"
        )
        .forEach(
            button =>
                button.onclick =
                    () => {
                        const p =
                            geo[
                                +button.dataset.guideCenter
                            ];

                        focusWorld(
                            worldPoint(p),
                            Math.max(
                                mapState.scale,
                                mapState.minScale * 3
                            )
                        );
                    }
        );

    $("#manualComplete").onchange =
        event =>
            saveManual(
                x,
                event.target.checked,
                $("#manualNoteInput").value
            );

    $("#saveManualNote").onclick =
        () =>
            saveManual(
                x,
                $("#manualComplete").checked,
                $("#manualNoteInput").value
            );
}

function renderManualSummary() {
    const entries =
        Object.values(
            manualTracking.entries || {}
        ),
        completed =
            entries.filter(
                x => x.completed
            ).length,
        notes =
            entries.filter(
                x => x.note
            ).length;

    $("#manualScore").textContent =
        `${completed.toLocaleString("en-US")} completed objective${completed === 1 ? "" : "s"}`;

    $("#manualNote").textContent =
        `${notes} note${notes === 1 ? "" : "s"} • revision ${manualTracking.revision} • separate from the automatic score`;

    $("#toggleManualReview").textContent =
        `Validations (${completed.toLocaleString("en-US")})`;

    renderManualReview();
}

function manualSearchText(value) {
    return String(value || "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLocaleLowerCase("en");
}

function manualCompletedRecords() {
    const items = new Map();

    allItems().forEach(item => {
        const id = itemId(item);

        if (!items.has(id)) {
            items.set(id, item);
        }
    });

    return Object.entries(manualTracking.entries || {})
        .filter(([_id, entry]) => entry.completed)
        .map(([trackingId, entry]) => {
            const item = items.get(trackingId),
                categoryId = item?.categorie || trackingId.split(":", 1)[0],
                categoryLabel =
                    report?.categories?.[categoryId]?.label ||
                    item?.filter_label ||
                    categoryId.replaceAll("_", " "),
                name =
                    item?.name ||
                    item?.display_name ||
                    item?.id ||
                    trackingId;

            return {
                trackingId,
                entry,
                item,
                categoryId,
                categoryLabel,
                name,
                region: item?.region || "",
                automatic: Boolean(item?.termine)
            };
        })
        .sort((left, right) => {
            const byDate = String(right.entry.updated_at || "")
                .localeCompare(String(left.entry.updated_at || ""));

            return byDate || left.name.localeCompare(right.name, "en");
        });
}

function manualDate(value) {
    if (!value) {
        return "unknown date";
    }

    const date = new Date(value);

    return Number.isNaN(date.getTime())
        ? "unknown date"
        : date.toLocaleString("en-US", {
            dateStyle: "short",
            timeStyle: "short"
        });
}

function renderManualReview() {
    const list = $("#manualReviewList"),
        categorySelect = $("#manualReviewCategory");

    if (!list || !categorySelect) {
        return;
    }

    const records = manualCompletedRecords(),
        selectedCategory = categorySelect.value || "all",
        categories = [...new Map(
            records.map(record => [
                record.categoryId,
                record.categoryLabel
            ])
        ).entries()].sort((left, right) => left[1].localeCompare(right[1], "en"));

    categorySelect.innerHTML =
        "<option value=\"all\">All categories</option>" +
        categories.map(
            ([id, label]) => `<option value="${esc(id)}">${esc(label)}</option>`
        ).join("");

    categorySelect.value = categories.some(([id]) => id === selectedCategory)
        ? selectedCategory
        : "all";

    const query = manualSearchText($("#manualReviewSearch").value),
        filtered = records.filter(record => {
            const matchesCategory =
                categorySelect.value === "all" ||
                record.categoryId === categorySelect.value,
                haystack = manualSearchText([
                    record.name,
                    record.categoryLabel,
                    record.region,
                    record.entry.note,
                    record.trackingId
                ].join(" "));

            return matchesCategory && (!query || haystack.includes(query));
        });

    $("#manualReviewSummary").textContent = records.length
        ? `${records.length.toLocaleString("en-US")} manual completion${records.length === 1 ? "" : "s"} • ${filtered.length.toLocaleString("en-US")} displayed`
        : "No lens manually checked.";

    if (!filtered.length) {
        list.innerHTML = `<div class="manualReviewEmpty">${records.length ? "No validation matches this search." : "Manually completed objectives will appear here."}</div>`;
        return;
    }

    list.innerHTML = filtered.map(record => {
        const status = record.item
            ? record.automatic
                ? "Also automatically validated"
                : "Not automatically validated"
            : "Missing from the current catalogue",
            meta = [
                record.region,
                status,
                manualDate(record.entry.updated_at)
            ].filter(Boolean).join(" • "),
            note = record.entry.note
                ? `<p class="manualReviewNote">Note : ${esc(record.entry.note)}</p>`
                : "";

        return `<article class="manualReviewItem"><div><span class="manualReviewCategory">${esc(record.categoryLabel)}</span><h3>${esc(record.name)}</h3><p>${esc(meta)}</p>${note}</div><div class="manualReviewItemActions"><button type="button" data-manual-open="${esc(record.trackingId)}"${record.item ? "" : " disabled"}>Open details</button><label class="manualReviewToggle"><input type="checkbox" checked data-manual-uncheck="${esc(record.trackingId)}"> Completed</label></div></article>`;
    }).join("");

    list.querySelectorAll("[data-manual-open]").forEach(button => {
        button.onclick = () => {
            closeManualReview(false);
            select(button.dataset.manualOpen, true);
        };
    });

    list.querySelectorAll("[data-manual-uncheck]").forEach(checkbox => {
        checkbox.onchange = () => uncheckManualFromReview(
            checkbox.dataset.manualUncheck,
            checkbox
        );
    });
}

function openManualReview() {
    manualReviewReturnFocus = document.activeElement;
    $("#manualReview").hidden = false;
    $("#toggleManualReview").setAttribute("aria-expanded", "true");
    renderManualReview();
    $("#manualReviewSearch").focus();
}

function closeManualReview(restoreFocus = true) {
    if ($("#manualReview").hidden) return;
    $("#manualReview").hidden = true;
    $("#toggleManualReview").setAttribute("aria-expanded", "false");
    if (restoreFocus) {
        const target = manualReviewReturnFocus || $("#toggleManualReview");
        requestAnimationFrame(() => target?.focus());
    }
    manualReviewReturnFocus = null;
}

async function uncheckManualFromReview(trackingId, checkbox) {
    const record = manualCompletedRecords().find(
        candidate => candidate.trackingId === trackingId
    );

    if (!record) {
        renderManualReview();
        return;
    }

    if (!confirm(
        `Clear the manual completion of “${record.name}”? Your personal note will be kept.`
    )) {
        checkbox.checked = true;
        return;
    }

    await saveManualById(
        trackingId,
        false,
        record.entry.note || "",
        record.item
    );
}

async function saveManualById(
    trackingId,
    completed,
    note,
    detailItem = null
) {
    try {
        const response =
            await fetch(
                `/api/manual/${encodeURIComponent(trackingId)}`,
                {
                    method: "PUT",
                    headers: {
                        "Content-Type":
                            "application/json"
                    },
                    body:
                        JSON.stringify({
                            completed,
                            note,
                            expected_revision:
                                manualTracking.revision
                        })
                }
            );

        const data =
            await response.json();

        if (!response.ok) {
            throw Error(
                data.erreur ||
                "Saving failed"
            );
        }

        manualTracking = data;

        renderAll();

        if (
            detailItem &&
            selectedId === trackingId
        ) {
            renderDetails(detailItem);
        }

        toast(
            completed
                ? "Manual validation registered"
                : "Manual Validation Cancelled"
        );

        return true;

    } catch (error) {
        toast(
            error.message,
            true
        );

        await load(false);
        return false;
    }
}

async function saveManual(
    x,
    completed,
    note
) {
    return saveManualById(
        itemId(x),
        completed,
        note,
        x
    );
}

async function importManualFile(file) {
    try {
        const imported =
            JSON.parse(
                await file.text()
            );

        if (
            imported?.application ===
            "BOTW Companion" &&
            imported?.manual_tracking &&
            imported?.route_sessions
        ) {
            const response = await fetch(
                "/api/backup/import",
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/json"
                    },
                    body: JSON.stringify({
                        backup: imported
                    })
                }
            );
            const data = await response.json();
            if (!response.ok) {
                throw Error(
                    data.erreur ||
                    "Restore failed"
                );
            }
            await load(false);
            toast(
                "Restored tracking, routes and preferences"
            );
            return;
        }

        const response =
            await fetch(
                "/api/manual/import",
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/json"
                    },
                    body:
                        JSON.stringify({
                            tracking: imported,
                            mode: "merge",
                            expected_revision:
                                manualTracking.revision
                        })
                }
            );

        const data =
            await response.json();

        if (!response.ok) {
            throw Error(
                data.erreur ||
                "Import failed"
            );
        }

        manualTracking = data;

        renderAll();

        toast(
            "Imported and merged manual tracking"
        );

    } catch (error) {
        toast(
            error.message ||
            "Invalid file",
            true
        );
    }
}

function formatDistance(value) {
    return value >= 1000
        ? `${(value / 1000).toFixed(value >= 10000 ? 1 : 2)} km`
        : `${Math.round(value)} m`
}

function toggleRouteItem(id) {
    const index =
        routeState.entries.findIndex(
            entry =>
                entry.tracking_id === id
        );

    if (index >= 0) {
        routeState.entries.splice(
            index,
            1
        );
    } else {
        const item =
            allItems().find(
                value =>
                    itemId(value) === id
            );

        if (
            !item ||
            item.x == null ||
            item.z == null
        ) {
            toast(
                "This element does not have reliable coordinates",
                true
            );

            return;
        }

        if (
            routeState.entries.length >=
            ROUTE_LIMIT
        ) {
            toast(
                `A session is limited to ${ROUTE_LIMIT} steps`,
                true
            );

            return;
        }

        routeState.entries.push({
            tracking_id: id,
            locked: false,
            snapshot:
                entrySnapshot(item)
        });
    }

    saveRouteState();
    renderRoute();
    renderItems();
}

function addFilteredToRoute() {
    const existing =
        routeIds(),
        available =
            filtered().filter(
                item =>
                    item.x != null &&
                    item.z != null &&
                    !existing.has(
                        itemId(item)
                    )
            );

    const capacity =
        Math.max(
            0,
            ROUTE_LIMIT -
            routeState.entries.length
        ),
        added =
            available.slice(
                0,
                capacity
            );

    routeState.entries.push(
        ...added.map(
            item => ({
                tracking_id:
                    itemId(item),
                locked: false,
                snapshot:
                    entrySnapshot(item)
            })
        )
    );

    saveRouteState();
    renderRoute();
    renderItems();

    if (!added.length) {
        toast(
            "No new localized results to add",
            true
        );
    } else {
        toast(
            `${added.length} step${added.length > 1 ? "s" : ""} added${available.length > capacity ? ` • limit of ${ROUTE_LIMIT} reached` : ""}`
        );
    }
}

function moveRouteEntry(
    index,
    delta
) {
    const target =
        index + delta;

    if (
        target < 0 ||
        target >=
        routeState.entries.length
    ) {
        return;
    }

    [
        routeState.entries[index],
        routeState.entries[target]
    ] = [
        routeState.entries[target],
        routeState.entries[index]
    ];

    saveRouteState();
    renderRoute();
    renderMap(filtered());
}

function lockRouteEntry(index) {
    routeState.entries[index].locked =
        !routeState.entries[index].locked;

    saveRouteState();
    renderRoute();
    renderMap(filtered());
}

function optimizeCurrentRoute() {
    const points =
        routePoints();

    if (points.length < 2) {
        toast(
            "Add at least two steps",
            true
        );

        return;
    }

    const optimized =
        RoutePlanner.optimize(
            points,
            routeState.start,
            routeState.strategy
        ),
        byId =
            new Map(
                routeState.entries.map(
                    entry => [
                        entry.tracking_id,
                        entry
                    ]
                )
            );

    let cursor = 0;

    routeState.entries =
        routeResolvedEntries().map(
            value =>
                value.item
                    ? byId.get(
                        optimized[
                            cursor++
                        ].tracking_id
                    )
                    : value.entry
        );

    saveRouteState();
    renderRoute();
    renderItems();

    toast(
        "Optimized order - locked and unavailable steps retained"
    );
}

function setRouteStart(point) {
    routeState.start =
        point
            ? {
                x: Number(point.x),
                z: Number(point.z),
                label:
                    point.label ||
                    point.name ||
                    "Custom Point"
            }
            : null;

    saveRouteState();
    renderRoute();
    renderMap(filtered());
}

function renderRoute() {
    if (!report) {
        return;
    }

    const resolved =
        routeResolvedEntries(),
        points =
            resolved
                .map(value => value.item)
                .filter(Boolean),
        legs =
            RoutePlanner.legs(
                points,
                routeState.start
            ),
        total =
            legs.at(-1)?.cumulative ||
            0;

    const legById =
        new Map(
            legs.map(
                leg => [
                    leg.point.tracking_id,
                    leg
                ]
            )
        ),
        missing =
            resolved.filter(
                value =>
                    !value.item
            ).length,
        regions =
            [
                ...new Set(
                    points
                        .map(
                            item =>
                                item.region
                        )
                        .filter(Boolean)
                )
            ];

    $("#routeSummary").textContent =
        points.length
            ? `${points.length} step${points.length > 1 ? "s" : ""} • ${formatDistance(total)}${missing ? ` • ${missing} unavailable` : ""}`
            : "No steps selected.";

    $("#routeSessionName").value =
        routeState.name;

    $("#routeStrategy").value =
        routeState.strategy ||
        "distance";

    $("#routeSessionSelect").innerHTML =
        Object.values(routesData.sessions)
            .sort(
                (a, b) =>
                    (b.updated_at || "")
                        .localeCompare(
                            a.updated_at || ""
                        )
            )
            .map(
                session =>
                    `<option value="${esc(session.id)}">${esc(session.name)} (${session.entries.length})</option>`
            )
            .join("");

    $("#routeSessionSelect").value =
        routeState.id;

    $("#routeStartLabel").textContent =
        `Departure: ${
            routeState.start
                ? `${routeState.start.label} - X ${Math.round(routeState.start.x)}, Z ${Math.round(routeState.start.z)}`
                : "premier objective"
        }`;

    $("#routeRegions").textContent =
        `Regions: ${
            regions.length
                ? regions.join(", ")
                : "-"
        }`;

    $("#routeStartX").value =
        routeState.start?.x ?? "";

    $("#routeStartZ").value =
        routeState.start?.z ?? "";

    $("#routeList").innerHTML =
        resolved.length
            ? resolved
                .map(
                    (value, index) => {
                        const entry =
                            value.entry,
                            stateIndex =
                                value.index,
                            leg =
                                value.item
                                    ? legById.get(
                                        entry.tracking_id
                                    )
                                    : null,
                            snapshot =
                                entry.snapshot || {},
                            name =
                                value.item?.name ||
                                snapshot.name ||
                                entry.tracking_id,
                            region =
                                value.item?.region ||
                                snapshot.region ||
                                "Unknown region";

                        return `<article class="routeStep ${value.item ? "" : "unavailable"}" data-route-step="${stateIndex}"><span>${index + 1}</span><div><b>${esc(name)}</b><small>${value.item ? `${esc(region)} • ${leg.index === 1 && !routeState.start ? "start" : `+ ${formatDistance(leg.distance)}`} • total ${formatDistance(leg.cumulative)}` : `Step unavailable in the current catalog • its previous information is retained`}</small></div><div class="routeStepActions">${value.item ? `<button data-route-focus="${esc(entry.tracking_id)}" title="View on map" aria-label="View ${esc(name)} on the map">⌖</button>` : ""}<button data-route-up="${stateIndex}" title="Move up" aria-label="Move up ${esc(name)}">↑</button><button data-route-down="${stateIndex}" title="Move down" aria-label="Move down ${esc(name)}">↓</button><button data-route-lock="${stateIndex}" class="${entry.locked ? "active" : ""}" title="Lock this position" aria-label="${entry.locked ? "Unlock" : "Lock"} the position of ${esc(name)}">${entry.locked ? "🔒" : "○"}</button><button data-route-remove="${esc(entry.tracking_id)}" title="Remove" aria-label="Remove ${esc(name)} from the route">×</button></div></article>`
                    }
                )
                .join("")
            : "<div class=\"empty\">Add goals from results or a record.</div>";

    document
        .querySelectorAll(
            "[data-route-focus]"
        )
        .forEach(
            button =>
                button.onclick =
                    () => {
                        const item =
                            allItems().find(
                                value =>
                                    itemId(value) ===
                                    button.dataset.routeFocus
                            );

                        if (item) {
                            select(
                                itemId(item)
                            );

                            focusItem(
                                item,
                                Math.max(
                                    mapState.scale,
                                    mapState.minScale * 3
                                )
                            );
                        }
                    }
        );

    document
        .querySelectorAll(
            "[data-route-up]"
        )
        .forEach(
            button =>
                button.onclick =
                    () =>
                        moveRouteEntry(
                            +button.dataset.routeUp,
                            -1
                        )
        );

    document
        .querySelectorAll(
            "[data-route-down]"
        )
        .forEach(
            button =>
                button.onclick =
                    () =>
                        moveRouteEntry(
                            +button.dataset.routeDown,
                            1
                        )
        );

    document
        .querySelectorAll(
            "[data-route-lock]"
        )
        .forEach(
            button =>
                button.onclick =
                    () =>
                        lockRouteEntry(
                            +button.dataset.routeLock
                        )
        );

    document
        .querySelectorAll(
            "[data-route-remove]"
        )
        .forEach(
            button =>
                button.onclick =
                    () =>
                        toggleRouteItem(
                            button.dataset.routeRemove
                        )
        );
}

function routeExportPayload() {
    const resolved =
        routeResolvedEntries(),
        points =
            resolved
                .map(
                    value => value.item
                )
                .filter(Boolean),
        legs =
            RoutePlanner.legs(
                points,
                routeState.start
            ),
        legById =
            new Map(
                legs.map(
                    leg => [
                        leg.point.tracking_id,
                        leg
                    ]
                )
            );

    return {
        schema_version: 2,
        application:
            "BOTW Companion",
        created_at:
            new Date().toISOString(),
        name:
            routeState.name,
        start:
            routeState.start,
        strategy:
            routeState.strategy,
        total_distance_m:
            Math.round(
                legs.at(-1)?.cumulative ||
                0
            ),
        regions: [
            ...new Set(
                points
                    .map(
                        item =>
                            item.region
                    )
                    .filter(Boolean)
            )
        ],
        steps:
            resolved.map(
                (value, index) => {
                    const leg =
                        legById.get(
                            value.entry.tracking_id
                        ),
                        snapshot =
                            value.entry.snapshot ||
                            {};

                    return {
                        order:
                            index + 1,
                        tracking_id:
                            value.entry.tracking_id,
                        name:
                            value.item?.name ||
                            snapshot.name ||
                            value.entry.tracking_id,
                        category:
                            value.item?.categorie ||
                            snapshot.category ||
                            null,
                        region:
                            value.item?.region ||
                            snapshot.region ||
                            null,
                        x:
                            value.item?.x ??
                            snapshot.x ??
                            null,
                        z:
                            value.item?.z ??
                            snapshot.z ??
                            null,
                        distance_from_previous_m:
                            leg
                                ? Math.round(
                                    leg.distance
                                )
                                : null,
                        cumulative_distance_m:
                            leg
                                ? Math.round(
                                    leg.cumulative
                                )
                                : null,
                        locked:
                            value.entry.locked,
                        available:
                            Boolean(value.item),
                        content_origin:
                            value.item?.content_origin ||
                            snapshot.content_origin ||
                            null
                    }
                }
            )
    };
}

function downloadRoute(format) {
    const payload =
        routeExportPayload();

    if (!payload.steps.length) {
        toast(
            "The route is empty",
            true
        );

        return;
    }

    const text =
        format === "json"
            ? JSON.stringify(
                payload,
                null,
                2
            )
            : [
                `BOTW COMPANION - ${payload.name}`,

                `Departure: ${
                    payload.start
                        ? `${payload.start.label} (X ${Math.round(payload.start.x)}, Z ${Math.round(payload.start.z)})`
                        : "premier objective"
                }`,

                `Geographic distance: ${formatDistance(payload.total_distance_m)}`,

                `Regions: ${payload.regions.join(", ")}`,

                "",

                ...payload.steps.map(
                    step =>
                        step.available
                            ? `${step.order}. ${step.name} - ${step.region || "region not indicated"} - X ${Number(step.x).toFixed(0)}, Z ${Number(step.z).toFixed(0)} - +${formatDistance(step.distance_from_previous_m)}${step.locked ? " - locked" : ""}`
                            : `${step.order}. ${step.name} - unavailable in the current catalog, retained${step.locked ? " - locked" : ""}`
                ),

                "",

                "Indicative distance: the strategy organizes the objectives but does not simulate any terrain, weather, climbing or dangers."

            ].join("\n");

    const blob =
        new Blob(
            [text],
            {
                type:
                    format === "json"
                        ? "application/json"
                        : "text/plain"
            }
        ),
        url =
            URL.createObjectURL(blob),
        link =
            document.createElement("a");

    link.href = url;

    link.download =
        `botw-session-${
            new Date()
                .toISOString()
                .slice(0, 10)
        }.${
            format === "json"
                ? "json"
                : "txt"
        }`;

    link.click();

    setTimeout(
        () =>
            URL.revokeObjectURL(url),
        0
    );
}

function routeSessionTemplate(
    name = "New session"
) {
    const id =
        `session-${
            crypto.randomUUID
                ? crypto.randomUUID()
                : Date.now() +
                    "-" +
                    Math.random()
                        .toString(16)
                        .slice(2)
        }`;

    return {
        id,
        name,
        start: null,
        strategy: "distance",
        entries: [],
        created_at:
            new Date().toISOString(),
        updated_at:
            new Date().toISOString()
    };
}

function activateRouteSession(id) {
    if (!routesData.sessions[id]) {
        return;
    }

    routesData.active_session_id = id;
    routeState =
        routesData.sessions[id];

    saveRouteState();
    renderRoute();
    renderItems();
    renderMap(filtered());
}

function createRouteSession(
    copy = false
) {
    if (
        Object.keys(
            routesData.sessions
        ).length >= 100
    ) {
        toast(
            "The planner is limited to 100 sessions",
            true
        );

        return;
    }

    const session =
        routeSessionTemplate(
            copy
                ? `${routeState.name} - copy`
                : "New session"
        );

    if (copy) {
        session.start =
            routeState.start
                ? {
                    ...routeState.start
                }
                : null;

        session.strategy =
            routeState.strategy;

        session.entries =
            routeState.entries.map(
                entry => ({
                    ...entry,
                    snapshot: {
                        ...(entry.snapshot || {})
                    }
                })
            );
    }

    routesData.sessions[
        session.id
    ] = session;

    routesData.active_session_id =
        session.id;

    routeState = session;

    saveRouteState();
    renderRoute();
    renderItems();

    toast(
        copy
            ? "Duplicate session"
            : "New session created"
    );
}

function deleteRouteSession() {
    if (
        Object.keys(
            routesData.sessions
        ).length === 1
    ) {
        toast(
            "Create another session before deleting it",
            true
        );

        return;
    }

    if (
        !confirm(
            `Permanently delete the session “${routeState.name}”?`
        )
    ) {
        return;
    }

    delete routesData.sessions[
        routeState.id
    ];

    routesData.active_session_id =
        Object.keys(
            routesData.sessions
        )[0];

    routeState =
        routesData.sessions[
            routesData.active_session_id
        ];

    saveRouteState();
    renderRoute();
    renderItems();
    renderMap(filtered());
}

async function importRouteFile(file) {
    try {
        const session =
            JSON.parse(
                await file.text()
            );

        await routeSaveQueue;

        const response =
            await fetch(
                "/api/routes/import",
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/json"
                    },
                    body:
                        JSON.stringify({
                            session,
                            expected_revision:
                                routesData.revision
                        })
                }
            ),
            data =
                await response.json();

        if (!response.ok) {
            throw Error(
                data.erreur ||
                "Import failed"
            );
        }

        routesData = data;

        routeState =
            routesData.sessions[
                routesData.active_session_id
            ];

        renderRoute();
        renderItems();
        renderMap(filtered());

        toast(
            "Imported session without removing existing routes"
        );

    } catch (error) {
        toast(
            error.message ||
            "Invalid route file",
            true
        );
    }
}

function closeDetails() {
    const d =
        $("#itemDetails");

    if (!d.classList.contains("open")) return;

    d.classList.remove("open");
    d.inert = true;

    d.setAttribute(
        "aria-hidden",
        "true"
    );

    if (selectedId !== null) {
        selectedId = null;

        if (report) {
            renderMap(filtered());
        }
    }

    const target = detailReturnTarget;
    detailReturnTarget = null;
    if (target) {
        const selector = target.manualReview
            ? `[data-manual-open="${CSS.escape(target.id)}"]`
            : target.fromList
                ? `[data-item-open="${CSS.escape(target.id)}"]`
                : `[data-map-id="${CSS.escape(target.id)}"]`;
        requestAnimationFrame(() => document.querySelector(selector)?.focus());
    }
}

function toast(
    text,
    error = false
) {
    const t =
        $("#toast");

    t.textContent = text;

    t.setAttribute(
        "role",
        error ? "alert" : "status"
    );

    t.style.background =
        error
            ? "#452522"
            : "";

    t.classList.add("show");

    setTimeout(
        () =>
            t.classList.remove("show"),
        2600
    )
}

const mapEl = $("#map");

mapEl.addEventListener(
    "pointerdown",
    e => {
        if (
            e.target.closest(".marker")
        ) {
            return;
        }

        mapState.dragging = true;
        mapState.moved = false;
        mapState.startX = e.clientX;
        mapState.startY = e.clientY;
        mapState.originX = mapState.x;
        mapState.originY = mapState.y;

        mapEl.classList.add(
            "dragging"
        );

        mapEl.setPointerCapture(
            e.pointerId
        );
    }
);

mapEl.addEventListener(
    "pointermove",
    e => {
        const r =
            mapRect(),
            wx =
                (
                    e.clientX -
                    r.left -
                    mapState.x
                ) /
                mapState.scale,
            wy =
                (
                    e.clientY -
                    r.top -
                    mapState.y
                ) /
                mapState.scale;

        if (
            wx >= 0 &&
            wx <= MAP_W &&
            wy >= 0 &&
            wy <= MAP_H
        ) {
            $("#mapCoords").textContent =
                `X ${Math.round(wx * 10 - 6000)} • Z ${Math.round(wy * 10 - 5000)} • zoom ${(mapState.scale / mapState.minScale).toFixed(1)}×`;
        }

        if (!mapState.dragging) {
            return;
        }

        if (
            Math.hypot(
                e.clientX -
                mapState.startX,
                e.clientY -
                mapState.startY
            ) > 5
        ) {
            mapState.moved = true;
        }

        mapState.x =
            mapState.originX +
            e.clientX -
            mapState.startX;

        mapState.y =
            mapState.originY +
            e.clientY -
            mapState.startY;

        applyMap();
    }
);

function stopDrag(e) {
    if (!mapState.dragging) {
        return;
    }

    mapState.dragging = false;

    mapEl.classList.remove(
        "dragging"
    );

    if (
        e.pointerId != null &&
        mapEl.hasPointerCapture(
            e.pointerId
        )
    ) {
        mapEl.releasePointerCapture(
            e.pointerId
        );
    }

    renderMap(filtered())
}

mapEl.addEventListener(
    "pointerup",
    stopDrag
);

mapEl.addEventListener(
    "pointercancel",
    stopDrag
);

mapEl.addEventListener(
    "click",
    e => {
        if (
            !routePickStart ||
            mapState.moved ||
            e.target.closest(".marker")
        ) {
            return;
        }

        const r =
            mapRect(),
            wx =
                (
                    e.clientX -
                    r.left -
                    mapState.x
                ) /
                mapState.scale,
            wy =
                (
                    e.clientY -
                    r.top -
                    mapState.y
                ) /
                mapState.scale;

        if (
            wx < 0 ||
            wx > MAP_W ||
            wy < 0 ||
            wy > MAP_H
        ) {
            return;
        }

        setRouteStart({
            x:
                Math.round(
                    wx * 10 - 6000
                ),
            z:
                Math.round(
                    wy * 10 - 5000
                ),
            label:
                "Point chosen on the map"
        });

        routePickStart = false;

        mapEl.classList.remove(
            "pickStart"
        );

        $("#pickRouteStart").classList.remove(
            "active"
        );

        toast(
            "Defined starting point"
        );
    }
);

mapEl.addEventListener(
    "wheel",
    e => {
        e.preventDefault();

        const r = mapRect();

        zoomMap(
            mapState.scale *
            (
                e.deltaY < 0
                    ? 1.22
                    : 1 / 1.22
            ),
            e.clientX - r.left,
            e.clientY - r.top
        )
    },
    {
        passive: false
    }
);

mapEl.addEventListener(
    "dblclick",
    e => {
        const r = mapRect();

        zoomMap(
            mapState.scale * 1.8,
            e.clientX - r.left,
            e.clientY - r.top
        )
    }
);

$("#zoomIn").onclick =
    () =>
        zoomMap(
            mapState.scale * 1.5
        );

$("#zoomOut").onclick =
    () =>
        zoomMap(
            mapState.scale / 1.5
        );

$("#mapReset").onclick =
    resetMap;

$("#closeDetails").onclick =
    closeDetails;

$("#toggleManualReview").onclick =
    openManualReview;

$("#closeManualReview").onclick =
    closeManualReview;

$("#manualReviewSearch").oninput =
    renderManualReview;

$("#manualReviewCategory").onchange =
    renderManualReview;

document.addEventListener(
    "keydown",
    e => {
        if (e.key === "Escape" && !$("#helpDialog").open && !tutorialState) {
            closeDetails();
            closeManualReview()
        }
    }
);

window.addEventListener(
    "resize",
    () => {
        if (mapState.ready) {
            resetMap()
        }
    }
);

$("#syncInterval").value =
    String(
        [
            5,
            10,
            15,
            30,
            60
        ].includes(syncInterval)
            ? syncInterval
            : 30
    );

syncInterval =
    Number(
        $("#syncInterval").value
    );

$("#mapDlcMode").value =
    [
        "automatique",
        "base",
        "dlc"
    ].includes(
        preferenceValue("map_content_mode", MAP_MODE_KEY, "automatique")
    )
        ? preferenceValue("map_content_mode", MAP_MODE_KEY, "automatique")
        : "automatique";

$("#mapDlcMode").onchange =
    () => {
        browserStorage.setItem(
            MAP_MODE_KEY,
            $("#mapDlcMode").value
        );
        savePreference("map_content_mode", $("#mapDlcMode").value);

        if (report) {
            renderAll()
        }
    };

$("#completionProfile").onchange =
    () => {
        browserStorage.setItem(
            PROFILE_KEY,
            $("#completionProfile").value
        );
        savePreference("completion_profile", $("#completionProfile").value);

        if (report) {
            renderAll()
        }
    };

$("#gameMode").onchange =
    () => {
        browserStorage.setItem(
            MODE_FILTER_KEY,
            $("#gameMode").value
        );
        savePreference("game_mode_filter", $("#gameMode").value);

        listRenderLimit =
            LIST_PAGE_SIZE;

        if (report) {
            renderFilterNav();
            renderItems()
        }
    };

$("#location").onchange =
    () => {
        listRenderLimit =
            LIST_PAGE_SIZE;

        if (report) {
            renderFilterNav();
            renderItems()
        }
    };

$("#syncInterval").onchange =
    () => {
        syncInterval =
            Number(
                $("#syncInterval").value
            );

        browserStorage.setItem(
            SYNC_INTERVAL_KEY,
            String(syncInterval)
        );
        savePreference("sync_interval", syncInterval);

        scheduleSync();

        toast(
            `Check every ${syncInterval} seconds`
        );
    };

$("#pauseSync").onclick =
    () => {
        syncPaused =
            !syncPaused;

        $("#pauseSync").textContent =
            syncPaused
                ? "Resume"
                : "Pause";

        $("#pauseSync").classList.toggle(
            "active",
            syncPaused
        );

        syncPaused
            ? clearTimeout(syncTimer)
            : checkSync(false);

        if (syncPaused) {
            toast(
                "Automatic pause synchronization"
            )
        }
    };

$("#quitCompanion").onclick =
    quitCompanion;

$("#dsuSource").onchange =
    () => {
        browserStorage.setItem(DSU_SOURCE_KEY, $("#dsuSource").value);
        refreshDsu();
    };

$("#toggleDsu").onclick =
    toggleDsu;

$("#openHelp").onclick =
    () => showHelp(null, $("#openHelp"));

$("#checkUpdates").onclick =
    () => checkForUpdates(true);

$("#downloadUpdate").onclick =
    handleUpdatePrimaryAction;

$("#cancelUpdateDownload").onclick =
    async () => {
        try {
            await updateDownloadAction("cancel");
        } catch (_error) {
            toast("Unable to cancel download", true);
        }
    };

$("#retryUpdateDownload").onclick =
    async () => {
        try {
            await updateDownloadAction("retry");
        } catch (_error) {
            toast("Unable to resume download", true);
        }
    };

$("#dismissUpdate").onclick =
    () => {
        const latest = availableUpdateVersion;
        if (latest) rememberDismissedUpdate(latest);
        $("#updateBanner").hidden = true;
        clearTimeout(updateDownloadTimer);
    };

$("#closeHelp").onclick =
    () => closeHelp(true);

$("#helpOverview").onclick =
    () => {
        renderHelpOverview();
        $("#helpContent").focus({ preventScroll: true });
    };

$("#helpChapterList").onclick =
    event => {
        const button = event.target.closest("[data-help-chapter]");
        if (button) renderHelpChapter(button.dataset.helpChapter);
    };

$("#helpContent").onclick =
    event => {
        const button = event.target.closest("[data-start-chapter]");
        if (button) startChapterTutorial(button.dataset.startChapter);
    };

$("#startTutorial").onclick =
    () => {
        tutorialResume = null;
        startEssentialTutorial(false, true);
    };

$("#resumeTutorial").onclick =
    () => startEssentialTutorial(true, true);

$("#helpDialog").addEventListener(
    "cancel",
    event => {
        event.preventDefault();
        closeHelp(true);
    }
);

$("#closeTutorial").onclick =
    () => closeTutorial({ persist: false });

$("#skipTutorial").onclick =
    () => closeTutorial({ persist: true, returnToHelp: false });

$("#previousTutorial").onclick =
    () => {
        if (!tutorialState) return;
        changeTutorialStep(Math.max(0, tutorialState.index - 1));
    };

$("#nextTutorial").onclick =
    () => {
        if (!tutorialState || tutorialTransition) return;
        if (tutorialState.index < tutorialState.steps.length - 1) {
            changeTutorialStep(tutorialState.index + 1);
        } else {
            closeTutorial({ persist: tutorialState.kind === "essential" });
        }
    };

$("#tutorialLayer").addEventListener(
    "keydown",
    event => {
        if (!tutorialState) return;
        if (event.key !== "Tab") return;
        const focusable = tutorialFocusableElements();
        if (!focusable.length) {
            event.preventDefault();
            $("#tutorialTitle").focus();
            return;
        }
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (!focusable.includes(document.activeElement)) {
            event.preventDefault();
            (event.shiftKey ? last : first).focus();
        } else if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    }
);

document.addEventListener(
    "keydown",
    event => {
        if (!tutorialState || event.key !== "Escape") return;
        event.preventDefault();
        event.stopPropagation();
        closeTutorial({ persist: false });
    },
    true
);

window.addEventListener("scroll", queueTutorialPosition, true);
window.addEventListener("resize", queueTutorialPosition);

document.addEventListener(
    "visibilitychange",
    () => {
        scheduleSync();

        clearTimeout(
            heartbeatTimer
        );

        sendHeartbeat();
        clearTimeout(dsuTimer);
        refreshDsu();

        if (
            !document.hidden &&
            !syncPaused
        ) {
            checkSync(false)
        }
    }
);

$("#refresh").onclick =
    () =>
        checkSync(true);

[
    "#search",
    "#status",
    "#dlc",
    "#variant",
    "#region"
].forEach(
    s =>
        $(s).addEventListener(
            s === "#search"
                ? "input"
                : "change",
            () => {
                listRenderLimit =
                    LIST_PAGE_SIZE;

                renderItems()
            }
        )
);

loadRuntimePlatform();
load();
refreshDsu();
refreshUpdateDownload();
checkForUpdates(false);

$("#exportManual").onclick =
    () => {
        window.location.href =
            "/api/manual/export"
    };

$("#importManual").onclick =
    () =>
        $("#manualFile").click();

$("#manualFile").onchange =
    event => {
        const file =
            event.target.files[0];

        if (file) {
            importManualFile(file)
        }

        event.target.value = ""
    };

$("#addFiltered").onclick =
    addFilteredToRoute;

$("#optimizeRoute").onclick =
    optimizeCurrentRoute;

$("#pickRouteStart").onclick =
    () => {
        routePickStart =
            !routePickStart;

        mapEl.classList.toggle(
            "pickStart",
            routePickStart
        );

        $("#pickRouteStart").classList.toggle(
            "active",
            routePickStart
        );

        toast(
            routePickStart
                ? "Click on the map to place the start"
                : "Selection of the cancelled departure"
        );
    };

$("#useSelectedStart").onclick =
    () => {
        const item =
            allItems().find(
                value =>
                    itemId(value) ===
                    selectedId
            );

        if (
            !item ||
            item.x == null
        ) {
            toast(
                "First open a localised file",
                true
            );

            return;
        }

        setRouteStart({
            x: item.x,
            z: item.z,
            label: item.name
        });

        toast(
            "Starting point set from the open detail panel"
        );
    };

$("#applyRouteStart").onclick =
    () => {
        const x =
            Number(
                $("#routeStartX").value
            ),
            z =
                Number(
                    $("#routeStartZ").value
                );

        if (
            !Number.isFinite(x) ||
            !Number.isFinite(z)
        ) {
            toast(
                "Enter valid X and Z coordinates",
                true
            );

            return;
        }

        setRouteStart({
            x,
            z,
            label:
                "Contact information"
        });

        toast(
            "Applied Start Coordinates"
        );
    };

$("#clearRouteStart").onclick =
    () => {
        setRouteStart(null);

        toast(
            "The first objective is used as the starting point."
        );
    };

$("#exportRouteJson").onclick =
    () =>
        downloadRoute("json");

$("#exportRouteText").onclick =
    () =>
        downloadRoute("text");

$("#importRouteJson").onclick =
    () =>
        $("#routeFile").click();

$("#routeFile").onchange =
    event => {
        const file =
            event.target.files[0];

        if (file) {
            importRouteFile(file)
        }

        event.target.value = ""
    };

$("#exportAllData").onclick =
    () => {
        window.location.href =
            "/api/backup/export"
    };

$("#routeSessionSelect").onchange =
    event =>
        activateRouteSession(
            event.target.value
        );

$("#routeSessionName").onchange =
    event => {
        const name =
            event.target.value.trim();

        if (!name) {
            event.target.value =
                routeState.name;

            toast(
                "The session name cannot be empty",
                true
            );

            return;
        }

        routeState.name = name;

        saveRouteState();
        renderRoute()
    };

$("#routeStrategy").onchange =
    event => {
        routeState.strategy =
            event.target.value;

        saveRouteState();

        toast(
            "Strategy recorded for this session"
        );
    };

$("#newRouteSession").onclick =
    () =>
        createRouteSession(false);

$("#duplicateRouteSession").onclick =
    () =>
        createRouteSession(true);

$("#deleteRouteSession").onclick =
    deleteRouteSession;

$("#clearRoute").onclick =
    () => {
        if (
            !routeState.entries.length ||
            confirm(
                "Empty all the steps of this session?"
            )
        ) {
            routeState.entries = [];

            saveRouteState();
            renderRoute();
            renderItems()
        }
    };

$("#toggleRoute").onclick =
    () => {
        const body =
            $("#routeBody"),
            hidden =
                body.hidden;

        body.hidden = !hidden;

        $("#toggleRoute").textContent =
            hidden
                ? "Hide"
                : "Show";

        $("#toggleRoute").setAttribute(
            "aria-expanded",
            String(hidden)
        );
    };

sendHeartbeat();
