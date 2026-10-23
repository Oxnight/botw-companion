const nativeFetch = window.fetch.bind(window);
const launchFragment = new URLSearchParams(window.location.hash.slice(1));
const sessionToken = document.querySelector('meta[name="botw-session-token"]')?.content ||
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
    label: BOTWI18n.t("app-local-system", {}),
    native_dsu_engine: "DSU",
    relaunch_hint: BOTWI18n.t("app-you-can-close-this-tab-relaunch-botw", {})
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
        if (manual) toast(BOTWI18n.t("showavailableupdate-the-update-response-is-not-valid", {}), true);
        return;
    }
    if (!manual && dismissedUpdateVersion() === data.latest_version) return;
    $("#updateTitle").textContent = data.title || `BOTW Companion ${data.latest_version}`;
    $("#updateVersions").textContent =
        BOTWI18n.t("showavailableupdate-installed-version-new-version", {value0: String(data.current_version), value1: String(data.latest_version)});
    availableUpdateVersion = data.latest_version;
    $("#downloadUpdate").disabled = false;
    $("#downloadUpdate").textContent = BOTWI18n.t("showavailableupdate-download-the-update", {});
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
            ? BOTWI18n.t("renderupdatedownload-install-and-restart", {})
            : BOTWI18n.t("renderupdatedownload-verified-download", {});
    } else if (active) {
        $("#downloadUpdate").textContent = state.status === "verifying" ? BOTWI18n.t("renderupdatedownload-checking", {}) : BOTWI18n.t("renderupdatedownload-downloading", {});
    } else {
        $("#downloadUpdate").textContent = BOTWI18n.t("renderupdatedownload-download-the-update", {});
    }
    const amount = state.bytes_total > 0
        ? BOTWI18n.t("renderupdatedownload-of", {value0: String(formatUpdateBytes(state.bytes_received)), value1: String(formatUpdateBytes(state.bytes_total)), value2: String(progress.toFixed(1))})
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
                ? BOTWI18n.t("renderupdatedownload-log", {value0: String(installation.log_path)})
                : "";
            toast((installation.message || BOTWI18n.t("renderupdatedownload-update-status-available", {})) + logHint,
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
        if (!response.ok) throw Error(BOTWI18n.t("refreshupdatedownload-service-unavailable", {}));
        renderUpdateDownload(await response.json());
    } catch (_error) {
        clearTimeout(updateDownloadTimer);
    }
}

async function updateDownloadAction(action) {
    const response = await fetch(`/api/update/download/${action}`, { method: "POST" });
    const state = await response.json();
    if (!response.ok) throw Error(state.erreur || BOTWI18n.t("updatedownloadaction-service-unavailable", {}));
    renderUpdateDownload(state);
    scheduleUpdateDownloadPoll();
}

async function startUpdateDownload() {
    try {
        await updateDownloadAction("start");
    } catch (_error) {
        toast(BOTWI18n.t("startupdatedownload-download-cannot-start-at-this-time", {}), true);
    }
}

async function installVerifiedUpdate() {
    const platformMessage = runtimePlatform.id === "macos"
        ? BOTWI18n.t("installverifiedupdate-a-separate-macos-stable-will-check-the", {}) +
          BOTWI18n.t("installverifiedupdate-then-restart-it-macos-can-ask-for", {})
        : BOTWI18n.t("installverifiedupdate-the-windows-wizard-will-then-open-and", {}) +
          BOTWI18n.t("installverifiedupdate-windows-will-not-be-restarted", {});
    if (updateInstallationPending || !confirm(
        BOTWI18n.t("installverifiedupdate-install-this-update-now", {}) +
        BOTWI18n.t("installverifiedupdate-botw-companion-and-joycondsu-will-shut-down", {}) +
        platformMessage
    )) return false;
    updateInstallationPending = true;
    clearTimeout(updateDownloadTimer);
    const button = $("#downloadUpdate");
    button.disabled = true;
    button.textContent = BOTWI18n.t("installverifiedupdate-preparing-installation", {});
    try {
        const response = await fetch("/api/update/install", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({client_id: window.BOTWBrowserSession.clientId})
        });
        const state = await response.json();
        if (!response.ok) throw Error(state.erreur || BOTWI18n.t("installverifiedupdate-service-unavailable", {}));
        $("#updateProgressText").textContent =
            state.message || BOTWI18n.t("installverifiedupdate-secure-shutdown-before-installation", {});
        window.BOTWBrowserSession.installed(state.browser_handoff);
        return true;
    } catch (error) {
        updateInstallationPending = false;
        button.disabled = false;
        button.textContent = BOTWI18n.t("installverifiedupdate-install-and-restart", {});
        toast(error.message || BOTWI18n.t("installverifiedupdate-installation-cannot-start", {}), true);
        return false;
    }
}

async function handleUpdatePrimaryAction() {
    if (updatePrimaryBusy || updateInstallationPending) return;
    updatePrimaryBusy = true;
    $("#downloadUpdate").disabled = true;
    try {
        const response = await fetch("/api/update/download");
        if (!response.ok) throw Error(BOTWI18n.t("handleupdateprimaryaction-service-unavailable", {}));
        const state = await response.json();
        if (state.status === "ready_to_install" && state.can_install) {
            await installVerifiedUpdate();
            return;
        }
        await startUpdateDownload();
    } catch (_error) {
        toast(BOTWI18n.t("handleupdateprimaryaction-the-update-cannot-start-at-this-time", {}), true);
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
        button.textContent = BOTWI18n.t("checkforupdates-checking", {});
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
                if (!response.ok) throw Error(BOTWI18n.t("checkforupdates-service-unavailable", {}));
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
            toast(BOTWI18n.t("checkforupdates-botw-companion-is-up-to-date", {}));
        } else if (manual && data.status === "unsupported") {
            toast(BOTWI18n.t("checkforupdates-automatic-verification-is-not-available-on-this", {}), true);
        } else if (manual) {
            toast(data.message || BOTWI18n.t("checkforupdates-unable-to-verify-at-the-moment", {}), true);
        }
    } catch (_error) {
        if (manual) {
            toast(BOTWI18n.t("checkforupdates-connection-unavailable-botw-companion-remains-usable-offline", {}), true);
        }
    } finally {
        clearTimeout(timer);
        if (manual) {
            button.disabled = false;
            button.textContent = BOTWI18n.t("checkforupdates-updates", {});
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
        name: BOTWI18n.t("loadroutestate-botw-session", {}),
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
                throw Error(data.erreur || BOTWI18n.t("savepreference-unable-to-save-preferences", {}));
            }
            preferencesData = data;
        })
        .catch(error => toast(error.message, true));
    return preferenceSaveQueue;
}

const HELP_CHAPTERS = [
    {
        id: "privacy",
        title: BOTWI18n.t("app-privacy-and-offline-mode", {}),
        summary: BOTWI18n.t("app-what-stays-on-your-device-and-what", {}),
        target: "header",
        points: [
            BOTWI18n.t("app-save-analysis-the-map-guides-manual-tracking", {}),
            BOTWI18n.t("app-your-game-saves-and-personal-companion-data", {}),
            BOTWI18n.t("app-a-connection-is-used-only-when-you", {})
        ],
        tip: BOTWI18n.t("app-the-companions-local-services-only-listen-to", {})
    },
    {
        id: "save",
        title: BOTWI18n.t("app-save-and-slot-analyzed", {}),
        summary: BOTWI18n.t("app-understand-the-detection-of-ryujinx-or-cemu", {}),
        target: "#savePreview",
        points: [
            BOTWI18n.t("app-the-top-panel-shows-the-detected-emulator", {}),
            BOTWI18n.t("app-botw-companion-compares-supported-save-files-and", {}),
            BOTWI18n.t("app-the-preview-date-and-source-help-you", {})
        ],
        tip: BOTWI18n.t("app-if-the-wrong-part-appears-check-the", {})
    },
    {
        id: "sync",
        title: BOTWI18n.t("app-synchronization-of-the-save", {}),
        summary: BOTWI18n.t("app-interval-pause-immediate-and-historical-reading", {}),
        target: ".syncSaveArea",
        points: [
            BOTWI18n.t("app-choose-the-interval-at-which-the-companion", {}),
            BOTWI18n.t("app-pause-suspends-automatic-readings-without-stopping-the", {}),
            BOTWI18n.t("app-recent-history-distinguishes-between-a-successful-read", {})
        ],
        tip: BOTWI18n.t("app-frequent-checking-does-not-speed-up-the", {})
    },
    {
        id: "completion",
        title: BOTWI18n.t("app-the-two-percentages", {}),
        summary: BOTWI18n.t("app-understand-the-difference-between-map-completion-and", {}),
        target: ".hero",
        points: [
            BOTWI18n.t("app-the-official-percentage-reproduces-botws-map-completion", {}),
            BOTWI18n.t("app-the-completion-profile-is-a-broader-indicator", {}),
            BOTWI18n.t("app-the-two-numbers-do-not-have-the", {})
        ],
        tip: BOTWI18n.t("app-expand-items-preventing-100-to-see-exactly", {})
    },
    {
        id: "sidebar",
        title: BOTWI18n.t("app-map-filters-and-side-navigation", {}),
        summary: BOTWI18n.t("app-quickly-choose-the-families-of-objectives-displayed", {}),
        target: "#categories",
        points: [
            BOTWI18n.t("app-the-column-to-the-left-of-the", {}),
            BOTWI18n.t("app-each-checkbox-shows-or-hides-an-entire", {}),
            BOTWI18n.t("app-the-counters-on-the-right-indicate-the", {})
        ],
        tip: BOTWI18n.t("app-start-by-checking-one-or-two-categories", {})
    },
    {
        id: "navigation",
        title: BOTWI18n.t("app-detailed-search-and-filters", {}),
        summary: BOTWI18n.t("app-refine-the-selected-categories-in-the-left", {}),
        target: ".toolbar",
        points: [
            BOTWI18n.t("app-after-choosing-the-categories-in-the-left", {}),
            BOTWI18n.t("app-filters-separate-states-additional-content-game-modes", {}),
            BOTWI18n.t("app-a-lens-can-be-automatic-manual-mixed", {})
        ],
        tip: BOTWI18n.t("app-start-with-a-category-then-refine-with", {})
    },
    {
        id: "map",
        title: BOTWI18n.t("app-hyrule-map", {}),
        summary: BOTWI18n.t("app-pan-and-zoom-the-map-use-markers", {}),
        target: ".mapPanel",
        points: [
            BOTWI18n.t("app-drag-and-drop-the-map-use-the", {}),
            BOTWI18n.t("app-markers-return-the-status-of-filtered-objectives", {}),
            BOTWI18n.t("app-some-objectives-take-place-in-an-interior", {})
        ],
        tip: BOTWI18n.t("app-the-map-and-all-its-tiles-are", {})
    },
    {
        id: "guides",
        title: BOTWI18n.t("app-objective-details-evidence-and-guides", {}),
        summary: BOTWI18n.t("app-read-the-status-solutions-and-their-limitations", {}),
        target: ".listPanel",
        points: [
            BOTWI18n.t("app-each-detail-panel-shows-the-detected-status", {}),
            BOTWI18n.t("app-automatic-proof-comes-from-the-save-it", {}),
            BOTWI18n.t("app-the-guides-may-include-external-sources-their", {})
        ],
        tip: BOTWI18n.t("app-limit-or-manual-validation-statements-are-voluntary", {})
    },
    {
        id: "manual",
        title: BOTWI18n.t("app-manual-tracking-and-data-backups", {}),
        summary: BOTWI18n.t("app-personal-checkboxes-notes-import-and-export", {}),
        target: ".manualBar",
        points: [
            BOTWI18n.t("app-manual-tracking-completes-the-analysis-without-changing", {}),
            BOTWI18n.t("app-you-can-review-validations-add-notes-and", {}),
            BOTWI18n.t("app-exports-allow-you-to-transfer-or-save", {})
        ],
        tip: BOTWI18n.t("app-regularly-save-all-data-if-you-plan", {})
    },
    {
        id: "routes",
        title: BOTWI18n.t("app-route-planner", {}),
        summary: BOTWI18n.t("app-create-order-and-maintain-gaming-sessions", {}),
        target: "#routePlanner",
        points: [
            BOTWI18n.t("app-add-filtered-results-or-a-specific-goal", {}),
            BOTWI18n.t("app-optimization-can-focus-on-direct-distance-regions", {}),
            BOTWI18n.t("app-the-calculation-is-indicative-it-does-not", {})
        ],
        tip: BOTWI18n.t("app-lock-mandatory-steps-before-optimizing-to-keep", {})
    },
    {
        id: "blood_moon",
        title: BOTWI18n.t("app-blood-looney", {}),
        summary: BOTWI18n.t("app-interpret-the-internal-counter-and-estimate", {}),
        target: "#bloodMoonPanel",
        points: [
            BOTWI18n.t("app-the-panel-reads-the-counter-recorded-by", {}),
            BOTWI18n.t("app-a-moon-can-be-programmed-and-then", {}),
            BOTWI18n.t("app-the-estimate-depends-on-the-last-save", {})
        ],
        tip: BOTWI18n.t("app-the-percentage-represents-the-progress-of-the", {})
    },
    {
        id: "dsu",
        title: BOTWI18n.t("ui-gyroscope-joycondsu", {}),
        summary: BOTWI18n.t("app-controller-calibration-diagnosis-and-emulator", {}),
        target: "#dsuControl",
        points: [
            BOTWI18n.t("app-select-a-compatible-controller-then-activate-the", {}),
            BOTWI18n.t("app-the-diagnosis-measures-frequency-delay-jitter-loss", {}),
            BOTWI18n.t("app-the-emulator-must-be-configured-for-the", {})
        ],
        tip: BOTWI18n.t("app-set-the-controller-to-stand-still-during", {})
    },
    {
        id: "application",
        title: BOTWI18n.t("app-updates-help-and-closure", {}),
        summary: BOTWI18n.t("app-manage-the-application-without-losing-your-data", {}),
        target: ".appActions",
        points: [
            BOTWI18n.t("app-updates-consults-the-latest-release-compatible-with", {}),
            BOTWI18n.t("app-the-help-button-reopens-this-center-so", {}),
            BOTWI18n.t("app-use-quit-to-cleanly-shut-down-the", {})
        ],
        tip: () => runtimePlatform.data_directory
            ? BOTWI18n.t("app-local-data-and-logs", {value0: String(runtimePlatform.data_directory)})
            : BOTWI18n.t("app-data-and-logs-are-kept-in-the", {})
    }
];

const ESSENTIAL_TUTORIAL_STEPS = [
    {
        chapter: "privacy",
        title: BOTWI18n.t("app-welcome-to-botw-companion", {}),
        description: BOTWI18n.t("app-the-companion-analyzes-your-progress-on-this", {}),
        detail: BOTWI18n.t("app-your-save-is-not-sent-only-updates", {}),
        target: "header"
    },
    {
        chapter: "save",
        title: BOTWI18n.t("app-check-the-save-retained", {}),
        description: BOTWI18n.t("app-the-emulator-slot-date-and-preview-confirm", {}),
        detail: () => {
            const save = report?.sauvegarde || {};
            return `${save.emulateur || BOTWI18n.t("app-detected-emulator", {})} • ${save.plateforme || runtimePlatform.label || BOTWI18n.t("app-local-system-2", {})} • slot ${save.slot || BOTWI18n.t("app-in-the-process-of-detection", {})}`;
        },
        target: "#savePreview"
    },
    {
        chapter: "sync",
        title: BOTWI18n.t("app-keep-progress-up-to-date", {}),
        description: BOTWI18n.t("app-choose-the-save-reading-interval-pause-synchronization", {}),
        detail: BOTWI18n.t("app-a-temporary-error-never-replaces-the-last", {}),
        target: ".syncSaveArea"
    },
    {
        chapter: "completion",
        title: BOTWI18n.t("app-two-measures-two-purposes", {}),
        description: BOTWI18n.t("app-the-golden-ring-reproduces-the-official-botw", {}),
        detail: BOTWI18n.t("app-their-totals-are-different-expands-the-blocking", {}),
        target: ".hero"
    },
    {
        chapter: "sidebar",
        title: BOTWI18n.t("app-select-the-categories-in-the-left-column", {}),
        description: BOTWI18n.t("app-the-side-navigation-boxes-show-or-hide", {}),
        detail: BOTWI18n.t("app-use-all-or-none-to-quickly-start", {}),
        target: "#categories"
    },
    {
        chapter: "navigation",
        title: BOTWI18n.t("app-find-out-what-interests-you", {}),
        description: BOTWI18n.t("app-after-selecting-categories-on-the-left-combine", {}),
        detail: BOTWI18n.t("app-the-automatic-manual-mixed-and-informative-states", {}),
        target: ".toolbar"
    },
    {
        chapter: "map",
        title: BOTWI18n.t("app-explore-the-map-and-objective-details", {}),
        description: BOTWI18n.t("app-move-and-zooms-the-map-then-selects", {}),
        detail: BOTWI18n.t("app-internal-or-untrusted-targets-remain-in-the", {}),
        target: ".mapPanel"
    },
    {
        chapter: "manual",
        title: BOTWI18n.t("app-keep-your-personal-validations", {}),
        description: BOTWI18n.t("app-manual-tracking-notes-and-exports-complete-the", {}),
        detail: BOTWI18n.t("app-the-planner-located-below-then-allows-to", {}),
        target: ".manualBar"
    },
    {
        chapter: "blood_moon",
        title: BOTWI18n.t("app-anticipate-the-blood-moon", {}),
        description: BOTWI18n.t("app-this-panel-interprets-the-timer-in-the", {}),
        detail: BOTWI18n.t("app-the-estimate-follows-the-known-active-play", {}),
        target: "#bloodMoonPanel"
    },
    {
        chapter: "dsu",
        title: BOTWI18n.t("app-activate-the-gyroscope-only-if-necessary", {}),
        description: BOTWI18n.t("app-joycondsu-is-included-but-remains-disabled-as", {}),
        detail: BOTWI18n.t("app-the-help-button-allows-you-to-find", {}),
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
        BOTWI18n.t("renderhelpoverview-good-start", {value0: String(`</p>`), value1: String(`<p class="eyebrow">`)}) +
        BOTWI18n.t("renderhelpoverview-choose-the-level-of-help-that-suits", {value0: String(`</h3>`), value1: String(`<h3>`)}) +
        BOTWI18n.t("renderhelpoverview-the-essential-tour-introduces-ten-key-areas", {value0: String(`</p>`), value1: String(`<p>`)}) +
        `<div class="helpOverviewCards">` +
        BOTWI18n.t("renderhelpoverview-guided-tour-10-contextual-steps-about-3", {value0: String(`</article>`), value1: String(`</span>`), value2: String(`<span>`), value3: String(`</b>`), value4: String(`<b>`), value5: String(`<article>`)}) +
        BOTWI18n.t("renderhelpoverview-help-center-13-complete-chapters-fully-offline", {value0: String(`</article>`), value1: String(`</span>`), value2: String(`<span>`), value3: String(`</b>`), value4: String(`<b>`), value5: String(`<article>`)}) +
        `</div>` +
        BOTWI18n.t("renderhelpoverview-no-action-is-triggered-during-the-tour", {value0: String(`</p>`), value1: String(`</b>`), value2: String(`<b>`), value3: String(`<p class="helpPrivacyNote">`)});
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
        BOTWI18n.t("renderhelpchapter-chapter", {value0: String(String(HELP_CHAPTERS.indexOf(chapter) + 1).padStart(2, "0")), value1: String(`</p>`), value2: String(`<p class="eyebrow">`)}) +
        `<h3>${esc(chapter.title)}</h3>` +
        `<p>${esc(chapter.summary)}</p>` +
        `<ul>${chapter.points.map(point => `<li>${esc(point)}</li>`).join("")}</ul>` +
        BOTWI18n.t("renderhelpchapter-to-remember", {value0: String(esc(tip)), value1: String(`</p>`), value2: String(`</b>`), value3: String(`<b>`), value4: String(`<p class="helpTip">`)}) +
        BOTWI18n.t("renderhelpchapter-view-in-the-interface", {value1: String(`</button>`), value2: String(`<button class="showHelpTarget" type="button" data-start-chapter="${esc(chapter.id)}">`)});
    if (focus) $("#helpContent").focus({ preventScroll: true });
}

function updateResumeTutorialButton() {
    const button = $("#resumeTutorial");
    if (!tutorialResume) {
        button.hidden = true;
        return;
    }
    button.hidden = false;
    button.textContent = BOTWI18n.t("updateresumetutorialbutton-resume-at-step", {value0: String(tutorialResume.index + 1)});
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
        ? BOTWI18n.t("rendertutorialstep-essential-tour", {})
        : BOTWI18n.t("rendertutorialstep-contextual-help", {});
    $("#tutorialStepLabel").textContent = BOTWI18n.t("rendertutorialstep-step-of", {value0: String(tutorialState.index + 1), value1: String(total)});
    $("#tutorialProgressBar").style.width = `${(tutorialState.index + 1) / total * 100}%`;
    $("#tutorialTitle").textContent = step.title;
    $("#tutorialDescription").textContent = step.description;
    $("#tutorialDetail").textContent = target
        ? detail
        : BOTWI18n.t("rendertutorialstep-this-part-of-the-interface-is-not", {value0: String(detail || "")}).trim();
    $("#previousTutorial").hidden = tutorialState.index === 0;
    $("#skipTutorial").hidden = tutorialState.kind !== "essential";
    $("#nextTutorial").textContent = last ? BOTWI18n.t("rendertutorialstep-finish", {}) : BOTWI18n.t("rendertutorialstep-next", {});
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
        throw Error(data.erreur || BOTWI18n.t("migratebrowserpreferences-migration-of-preferences-is-impossible", {}));
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
            label: BOTWI18n.t("filtergroupsfordisplay-completed-shrines-remaining-chests", {}),
            count: remaining.length
        });
        treasures.types.sort(
            (left, right) =>
                left.label.localeCompare(
                    right.label,
                    BOTWI18n.formatLocale
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
        mixed: BOTWI18n.t("trackinglabel-automatic-manual", {}),
        automatic: BOTWI18n.t("trackinglabel-automatic", {}),
        manual: BOTWI18n.t("trackinglabel-manual", {}),
        none: x.informational ? BOTWI18n.t("trackinglabel-informational", {}) : BOTWI18n.t("trackinglabel-to-do", {})
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
                    BOTWI18n.t("saveroutestate-routes-cannot-be-recorded", {})
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
    ].sort((a, b) => a.localeCompare(b, BOTWI18n.formatLocale));

    select.innerHTML =
        BOTWI18n.t("refreshvariants-all-variants", {value0: String(`</option>`), value1: String(`<option value="all">`)}) +
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
                    profile.available === false ? 'disabled' : ''
                }>${esc(profile.label)}${
                    profile.available === false
                        ? BOTWI18n.t("refreshprofileselect-unavailable", {})
                        : ''
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
            label: profile?.label || BOTWI18n.t("selectedcompletionscore-profile", {}),
            note: p.mode || BOTWI18n.t("selectedcompletionscore-profile-unavailable", {})
        };
    }

    const formula = report.referentiel_100.formula.expression,
        inventory = report.referentiel_100.inventory_constraints,
        inventoryNote = profile.id === "amiibo"
            ? BOTWI18n.t("selectedcompletionscore-separate-collection-armor-pieces-exist-for-slots", {value0: String(inventory.all_unique_armor), value1: String(inventory.armor_inventory_limit)})
            : "";
    return {
        available: true,
        label: profile.label,
        faits: p.faits || 0,
        total: p.total || 0,
        pourcentage: p.total
            ? 100 * p.faits / p.total
            : 0,
        note: BOTWI18n.t("selectedcompletionscore-formula", {value0: String(profile.scope), value1: String(formula), value2: String(inventoryNote)}),
        blockers: p.blocking_categories || [], remaining: p.remaining || 0,
        effectiveProfile: p.effective_profile || profile.id, profileId: profile.id
    };
}

function renderCompletionBlockers(score) {
    const summary = $("#completionBlockerSummary"), list = $("#completionBlockerList"),
        details = $("#completionBlockers");
    if (!score.available) {
        summary.textContent = BOTWI18n.t("rendercompletionblockers-profile-unavailable-for-this-save", {});
        list.innerHTML = ""; details.open = false; return;
    }
    if (!score.remaining) {
        summary.textContent = BOTWI18n.t("rendercompletionblockers-there-is-nothing-to-prevent-the-100", {});
        list.innerHTML = BOTWI18n.t("rendercompletionblockers-this-profile-is-complete", {value0: String(`</li>`), value1: String(`<li>`)}); details.open = false; return;
    }
    summary.textContent = BOTWI18n.t("rendercompletionblockers-items-prevent-100-completion", {value0: String(score.remaining.toLocaleString(BOTWI18n.formatLocale))});
    list.innerHTML = score.blockers.map(category => {
        const examples = category.examples.map(item => esc(item.name)).join(" • "),
            more = Math.max(0, category.remaining - category.examples.length);
        return `<li><b>${esc(category.label)} : ${category.remaining.toLocaleString(BOTWI18n.formatLocale)}</b>` +
            `<span>${examples}${more ? BOTWI18n.t("rendercompletionblockers-more", {value0: String(more.toLocaleString(BOTWI18n.formatLocale))}) : ""}</span></li>`;
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
            BOTWI18n.t("renderbloodmoon-estimation-unavailable", {});

        $("#bloodMoonStatus").textContent =
            moon.status_label ||
            BOTWI18n.t("renderbloodmoon-internal-counter-unavailable", {});

        $("#bloodMoonPhase").textContent =
            BOTWI18n.t("renderbloodmoon-unavailable", {});

        $("#bloodMoonPercent").textContent = "-";
        $("#bloodMoonThreshold").textContent = "-";
        $("#bloodMoonScheduled").textContent = "-";
        $("#bloodMoonEvent").textContent = "-";

        $("#bloodMoonMeasuredAt").textContent =
            BOTWI18n.t("renderbloodmoon-no-measurements-available", {});

        $("#bloodMoonInternal").textContent =
            BOTWI18n.t("renderbloodmoon-no-value-exploitable-in-the-last-save", {});

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
            ? BOTWI18n.t("renderbloodmoon-validated-cycle-programmed", {})
            : moon.status === "just_occurred"
                ? BOTWI18n.t("renderbloodmoon-new-cycle", {})
                : BOTWI18n.t("renderbloodmoon-current-cycle-unscheduled", {});

    $("#bloodMoonCountdown").textContent =
        BOTWI18n.t("renderbloodmoon-of-active-play", {value0: String(duration)});

    $("#bloodMoonPhase").textContent = phase;

    $("#bloodMoonPercent").textContent =
        `${Math.round(
            Number(moon.timer_progress_percent) || 0
        )} %`;

    $("#bloodMoonStatus").textContent =
        moon.scheduled
            ? BOTWI18n.t("renderbloodmoon-the-blood-moon-is-validated-it-will", {})
            : BOTWI18n.t("renderbloodmoon-estimated-time-remaining-since-the-last-save", {});

    $("#bloodMoonThreshold").textContent =
        moon.scheduled
            ? BOTWI18n.t("renderbloodmoon-reached", {})
            : BOTWI18n.t("renderbloodmoon-in", {value0: String(bloodMoonDuration(
                moon.active_seconds_until_threshold
            ))});

    $("#bloodMoonScheduled").textContent =
        moon.scheduled
            ? BOTWI18n.t("renderbloodmoon-validated", {})
            : BOTWI18n.t("renderbloodmoon-in-2", {value0: String(bloodMoonDuration(
                moon.active_seconds_until_scheduled
            ))});

    $("#bloodMoonEvent").textContent =
        BOTWI18n.t("renderbloodmoon-in-3", {value0: String(duration)});

    $("#bloodMoonMeasuredAt").textContent =
        savedAt !== "-"
            ? BOTWI18n.t("renderbloodmoon-exact-value-from-the-save-at", {value0: String(savedAt)})
            : BOTWI18n.t("renderbloodmoon-exact-measurement-of-the-last-save", {});

    $("#bloodMoonInternal").textContent =
        BOTWI18n.t("renderbloodmoon-counter-game-time", {value0: String(Number(moon.timer_value).toLocaleString(
                BOTWI18n.formatLocale,
                {
                    maximumFractionDigits: 1
                }
            )), value1: String(Number(moon.timer_target).toLocaleString(BOTWI18n.formatLocale)), value2: String(moon.game_time_label)});

    $("#bloodMoonAccuracy").textContent =
        BOTWI18n.t("renderbloodmoon-the-counter-decreases-only-during-active-play", {value0: String(moon.may_be_delayed
                ? BOTWI18n.t("renderbloodmoon-the-trigger-is-currently-subject-to-postponement", {})
                : "")});

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
        option.textContent = BOTWI18n.t("renderdsusources-no-controller-detected", {});
        select.appendChild(option);
        select.value = "";
        $("#dsuCapabilities").textContent =
            BOTWI18n.t("renderdsusources-connect-a-controller-via-usb-or-bluetooth", {});
        return null;
    }

    for (const controller of controllers) {
        const option = document.createElement("option");
        option.value = String(controller.id);
        const suffix = controller.compatible
            ? BOTWI18n.t("renderdsusources-gyroscope-available", {})
            : controller.kind === "joycon_single"
                ? BOTWI18n.t("renderdsusources-combine-the-two-joy-cons", {})
                : BOTWI18n.t("renderdsusources-gyroscope-unavailable", {});
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
        ? BOTWI18n.t("renderdsusources-joy-con-pair-grip", {})
        : chosen.type || BOTWI18n.t("renderdsusources-controller", {});
    $("#dsuCapabilities").textContent = chosen.compatible
        ? BOTWI18n.t("renderdsusources-gyroscope-and-accelerometer-available", {value0: String(kind), value1: String(vidPid)})
        : chosen.kind === "joycon_single"
            ? BOTWI18n.t("renderdsusources-uses-the-combined-joy-con-pair", {value0: String(kind), value1: String(vidPid)})
            : BOTWI18n.t("renderdsusources-no-gyroscope-usable-by-sdl3", {value0: String(kind), value1: String(vidPid)});
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
    return Number.isFinite(numeric) ? numeric.toLocaleString(BOTWI18n.formatLocale) : "-";
}

function renderDsuDiagnostic(state) {
    const diagnostic = state?.diagnostic || {
        status: "inactive",
        label: BOTWI18n.t("renderdsudiagnostic-inactive-diagnostic", {}),
        summary: BOTWI18n.t("renderdsudiagnostic-enable-the-gyroscope-to-measure-signal-quality", {})
    };
    const telemetry = state?.telemetry || {};
    const quality = $("#dsuQuality");
    quality.textContent = diagnostic.label;
    quality.className = `quality-${diagnostic.status}`;
    $("#dsuQualitySummary").textContent = diagnostic.summary;
    $("#dsuReceivedRate").textContent = dsuMetric(telemetry.received_hz, 1, " Hz");
    $("#dsuSentRate").textContent = Number(telemetry.clients || 0) === 0 && telemetry.sent_hz !== undefined
        ? BOTWI18n.t("renderdsudiagnostic-waiting-for-the-emulator", {})
        : dsuMetric(telemetry.sent_hz, 1, " Hz");
    $("#dsuSampleAge").textContent = dsuMetric(telemetry.sample_age_ms, 1, " ms");
    $("#dsuReceivedJitter").textContent = telemetry.received_jitter_mean_ms === undefined
        ? "-"
        : BOTWI18n.t("renderdsudiagnostic-avg-max", {value0: String(dsuMetric(telemetry.received_jitter_mean_ms, 2, " ms")), value1: String(dsuMetric(telemetry.received_jitter_max_ms, 2, " ms"))});
    $("#dsuSentJitter").textContent = telemetry.sent_jitter_mean_ms === undefined
        ? "-"
        : BOTWI18n.t("renderdsudiagnostic-avg-max-2", {value0: String(dsuMetric(telemetry.sent_jitter_mean_ms, 2, " ms")), value1: String(dsuMetric(telemetry.sent_jitter_max_ms, 2, " ms"))});
    $("#dsuTimestampErrors").textContent = telemetry.duplicate_timestamps === undefined
        ? "-"
        : BOTWI18n.t("renderdsudiagnostic-duplicates-timestamps-out-of-order", {value0: String(dsuCounter(telemetry.duplicate_timestamps)), value1: String(dsuCounter(telemetry.regressive_timestamps))});
    $("#dsuSentPackets").textContent = dsuCounter(telemetry.sent_packets);
    $("#dsuNetworkErrors").textContent = telemetry.send_errors === undefined
        ? "-"
        : BOTWI18n.t("renderdsudiagnostic-udp-invalid-requests", {value0: String(dsuCounter(telemetry.send_errors)), value1: String(dsuCounter(telemetry.invalid_requests))});
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
        state_label: BOTWI18n.t("renderdsu-inaccessible-dsu-status", {}),
        message: BOTWI18n.t("renderdsu-the-companion-cannot-query-the-local-server", {}),
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
        state.log_path ? BOTWI18n.t("renderdsu-log", {value0: String(state.log_path)}) : null
    ].filter(Boolean).join("\n");
    $("#toggleDsu").textContent = state.running ? BOTWI18n.t("renderdsu-disable", {}) : BOTWI18n.t("renderdsu-enable", {});
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
            throw Error(BOTWI18n.t("loadruntimeplatform-platform-unavailable", {}));
        }
        runtimePlatform = {
            ...runtimePlatform,
            ...(data.platform || {})
        };
        $("#runtimePlatform").textContent =
            String(runtimePlatform.label || BOTWI18n.t("loadruntimeplatform-local-system", {})).toUpperCase();
        $("#dsuEngineLabel").textContent =
            runtimePlatform.native_dsu_engine || "DSU";
    } catch (_error) {
        $("#runtimePlatform").textContent = BOTWI18n.t("loadruntimeplatform-local-system-2", {});
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
        throw Error(BOTWI18n.t("copytext-unable-to-copy-in-this-browser", {}));
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
            throw Error(state.message || BOTWI18n.t("refreshdsu-inaccessible-dsu-status", {}));
        }
        renderDsu(state);
    } catch (error) {
        if (controller.signal.aborted) return;
        renderDsu({
            state: "error",
            state_label: BOTWI18n.t("refreshdsu-inaccessible-dsu-status-2", {}),
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
            throw Error(state.message || BOTWI18n.t("toggledsu-dsu-command-failed", {}));
        }
        toast(stop ? BOTWI18n.t("toggledsu-gyroscope-disabled", {}) : BOTWI18n.t("toggledsu-dsu-server-enabled-leaves-the-controller-motionless", {}));
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
                BOTWI18n.t("load-inaccessible-preferences", {})
            );
        }

        preferencesData = preferences;
        const language = BOTWI18n.locale;
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
                toast(BOTWI18n.t("load-the-language-for-startup-dialogs-could-not", {}), true);
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
                BOTWI18n.t("load-analysis-failed", {})
            );
        }

        if (!manualResponse.ok) {
            throw Error(
                manual.erreur ||
                BOTWI18n.t("load-manual-tracking-unavailable", {})
            );
        }

        if (!routesResponse.ok) {
            throw Error(
                routes.erreur ||
                BOTWI18n.t("load-inaccessible-routes", {})
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
                BOTWI18n.t("load-catalog-unavailable", {})
            );
        }

        if (
            catalog.report_revision_key !==
            data.report_revision_key
        ) {
            throw Error(
                BOTWI18n.t("load-the-save-has-changed-during-catalog-loading", {})
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
                BOTWI18n.t("load-old-route-transferred-in-the-application-data", {})
            );
        }

        renderAll();

        if (showToast) {
            toast(
                BOTWI18n.t("load-back-up-and-restore-manual-tracking-and", {})
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
        BOTWI18n.t("ui-slot-2", {value0: String(s.slot), value1: String(s.mode === "expert"
                ? BOTWI18n.t("renderall-master-mode", {})
                : BOTWI18n.t("renderall-normal-mode", {})), value2: String(saveDate), value3: String(s.chemin)});

    renderSavePreview(s, saveDate);

    const emulatorLabel = String(s.emulateur || BOTWI18n.t("renderall-emulator", {})).toUpperCase();
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
        BOTWI18n.t("renderall-markers-on", {value0: String(mapScore.faits.toLocaleString(BOTWI18n.formatLocale)), value1: String(mapScore.total.toLocaleString(BOTWI18n.formatLocale))});

    const formula =
        mapScore.selected_mode === "dlc"
            ? BOTWI18n.t("renderall-base-game-dlc-formula", {})
            : BOTWI18n.t("renderall-formula-basic-game", {});

    $("#mapStatus").textContent =
        mapScore.visible_dans_le_jeu
            ? BOTWI18n.t("renderall-official-percentage-of-the-map-currently-visible", {value0: String(formula), value1: String(mapScore.selection === "automatique"
                    ? BOTWI18n.t("renderall-selected-automatically", {})
                    : BOTWI18n.t("renderall-imposed-manually", {}))})
            : BOTWI18n.t("renderall-exact-prediction-of-map-completion-this-counter", {value0: String(formula), value1: String(mapScore.selection === "automatique"
                    ? BOTWI18n.t("renderall-selected-automatically-2", {})
                    : BOTWI18n.t("renderall-imposed-manually-2", {}))});

    const labels = {
        korogus: BOTWI18n.t("renderall-koroks", {}),
        sanctuaires_base: BOTWI18n.t("renderall-shrines", {}),
        marqueurs_carte:
            BOTWI18n.t("renderall-places-towers-creatures", {}),
        sanctuaires_dlc:
            BOTWI18n.t("renderall-shrines-dlc", {}),
        donjon_final_dlc:
            BOTWI18n.t("renderall-final-dlc-dungeon", {})
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
            ? BOTWI18n.t("renderall-completed-items-out-of", {value0: String(score.faits.toLocaleString(BOTWI18n.formatLocale)), value1: String(score.total.toLocaleString(BOTWI18n.formatLocale))})
            : BOTWI18n.t("renderall-unavailable-for-this-save", {value0: String(score.label)});

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
        BOTWI18n.t("renderall-all-regions", {value0: String(`</option>`), value1: String(`<option value="all">`)}) +
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
    const mode = save.mode === "expert" ? BOTWI18n.t("rendersavepreview-master-mode", {}) : BOTWI18n.t("rendersavepreview-normal-mode", {}),
        emulator = save.emulateur || BOTWI18n.t("rendersavepreview-emulator", {}),
        platform = save.plateforme || runtimePlatform.label || BOTWI18n.t("rendersavepreview-local-system", {}),
        revision = String(report.report_revision_key || `${save.slot}:${save.date}`),
        image = $("#saveCaption"),
        fallback = $("#saveCaptionFallback");

    $("#saveSlotTitle").textContent = BOTWI18n.t("rendersavepreview-slot", {value0: String(save.slot), value1: String(mode)});
    $("#saveSlotDate").textContent = BOTWI18n.t("rendersavepreview-latest-save", {value0: String(saveDate)});
    $("#saveSlotSource").textContent = `${emulator} • ${platform}`;
    $("#savePreview").title = save.detection_mode || BOTWI18n.t("rendersavepreview-slot-selected-automatically", {});
    fallback.textContent = BOTWI18n.t("ui-slot", {value0: String(save.slot)});

    if (saveCaptionRevision === revision) {
        return;
    }

    saveCaptionRevision = revision;
    image.hidden = true;
    fallback.hidden = false;
    image.alt = BOTWI18n.t("rendersavepreview-preview-of-slot-mode-saved-on", {value0: String(save.slot), value1: String(mode), value2: String(saveDate)});
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
            BOTWI18n.formatLocale,
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
    const localDate = new Intl.DateTimeFormat(BOTWI18n.formatLocale, {
        dateStyle: "short"
    }).format(date);
    const localTime = new Intl.DateTimeFormat(BOTWI18n.formatLocale, {
        timeStyle: "medium"
    }).format(date);
    return BOTWI18n.t("localsavedatetime-at", {value0: String(localDate), value1: String(localTime)});
}

function localSaveTime(timestamp, fallback = null) {
    const numeric = Number(timestamp);
    const date = Number.isFinite(numeric) && numeric > 0
        ? new Date(numeric * 1000)
        : (fallback ? new Date(fallback) : null);
    if (!date || Number.isNaN(date.getTime())) return "-";
    return new Intl.DateTimeFormat(BOTWI18n.formatLocale, {
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
            ? BOTWI18n.t("updatesync-synchronization-temporarily-unavailable", {})
            : meta.status_label ||
                BOTWI18n.t("updatesync-first-reading-pending", {});

    $("#syncDot").className =
        `sync-${status}`;

    const mode =
        meta.save_mode === "expert"
            ? BOTWI18n.t("updatesync-master-mode", {})
            : meta.save_mode === "normal"
                ? "normal"
                : "-";

    const candidate =
        meta.candidate_slot
            ? BOTWI18n.t("updatesync-candidate", {value0: String(meta.candidate_slot)})
            : "";

    $("#syncTimes").textContent =
        error
            ? BOTWI18n.t("updatesync-last-report-retained", {value0: String(error)})
            : BOTWI18n.t("updatesync-last-successful-read-at-internal-save-at", {value0: String(syncDate(meta.last_success_at)), value1: String(localSaveTime(meta.save_timestamp, meta.save_timestamp_at)), value2: String(meta.slot || "-"), value3: String(mode), value4: String(candidate), value5: String(meta.report_revision || 0)});

    const events = meta.events || [];

    $("#syncEvents").innerHTML =
        events.length
            ? events
                .map(
                    event =>
                        `<p><time>${esc(syncDate(event.at))}</time><span>${esc(event.message)}</span></p>`
                )
                .join("")
            : BOTWI18n.t("updatesync-no-event", {value0: String(`</p>`), value1: String(`<p>`)});
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
            BOTWI18n.t("quitcompanion-stop-botw-companion-manual-tracking-and-previously", {})
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
        BOTWI18n.t("quitcompanion-botw-companion-has-stopped", {value0: String(esc(runtimePlatform.relaunch_hint)), value1: String(`</main>`), value2: String(`</div>`), value3: String(`</p>`), value4: String(`<p>`), value5: String(`</h1>`), value6: String(`<h1>`), value7: String(`<div class="panel">`), value8: String(`<main class="shutdownPage">`)});
}

async function checkSync(force = false) {
    $("#refresh").disabled = true;

    if (force) {
        updateSync({
            status: "analyse",
            status_label:
                BOTWI18n.t("checksync-immediate-reading-required", {}),
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
                BOTWI18n.t("checksync-synchronization-failed", {})
            );
        }

        if (data.changed) {
            await load(false);

            toast(
                BOTWI18n.t("checksync-new-save-analyzed-and-updated-catalog", {})
            );
        } else {
            updateSync(data.synchronisation);

            if (force) {
                toast(
                    BOTWI18n.t("checksync-re-read-save-unchanged-content", {})
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
                                        ? `${done.toLocaleString(BOTWI18n.formatLocale)}/${trackable.length.toLocaleString(BOTWI18n.formatLocale)}`
                                        : `${items.length.toLocaleString(BOTWI18n.formatLocale)} pts`,
                                hint =
                                    trackable.length
                                        ? BOTWI18n.t("renderfilternav-completed-of", {value0: String(done), value1: String(done > 1 ? 's' : ''), value2: String(trackable.length), count: done})
                                        : BOTWI18n.t("renderfilternav-informational-point-no-completion-status", {value0: String(items.length), value1: String(items.length > 1 ? 's' : ''), value2: String(items.length > 1 ? 's' : ''), count: items.length});

                            return `<label class="filterType ${selectedTypes.has(type.id) ? 'selected' : ''}" title="${esc(hint)}"><input type="checkbox" data-filter-type="${esc(type.id)}" ${selectedTypes.has(type.id) ? 'checked' : ''}><span>${esc(type.label)}</span><small class="filterProgress ${trackable.length ? '' : 'informational'}">${progress}</small></label>`
                        })
                        .join("");

                return BOTWI18n.t("renderfilternav-filters", {value0: String(esc(group.label)), value1: String(checked), value2: String(visibleTypes.length), value3: String(types), value4: String(`</details>`), value5: String(`</div>`), value6: String(`<div>`), value7: String(`</summary>`), value8: String(`</small>`), value10: String(`<small title="${BOTWI18n.t("renderfilternav-active-filters", {})}">`), value11: String(`</span>`), value12: String(`<span>`), value13: String(`<summary>`), value14: String(`<details class="filterGroup" open>`)});
            })
            .join("");

    $("#categories").innerHTML =
        BOTWI18n.t("renderfilternav-map-filters-all-none", {value0: String(groups), value1: String(`</div>`), value2: String(`</span>`), value3: String(`</button>`), value4: String(`<button data-filter-action="none">`), value5: String(`</button>`), value6: String(`<button data-filter-action="all">`), value7: String(`<span>`), value8: String(`</b>`), value9: String(`<b>`), value10: String(`<div class="filterHeading">`)});

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
            ? BOTWI18n.t("armorline-materials-ready", {})
            : "";

    return `${x.etoiles || "☆☆☆☆"}${
        x.possede
            ? BOTWI18n.t("armorline-level-4", {value0: String(x.niveau)})
            : BOTWI18n.t("armorline-not-possessed", {})
    }${ready}`;
}

function renderItems() {
    refreshVariants();

    const items = filtered();

    $("#resultCount").textContent =
        BOTWI18n.t("renderitems-result", {value0: String(items.length), value1: String(items.length > 1 ? 's' : ''), count: items.length});

    $("#mapCount").textContent =
        BOTWI18n.t("renderitems-with-coordinates", {value0: String(items.filter(x => x.x != null && x.z != null).length)});

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
            : BOTWI18n.t("renderitems-filtered-elements", {});

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
                                ? BOTWI18n.t("renderitems-near", {value0: String(x.nearby)})
                                : null,
                            x.trial,
                            x.quest,
                            x.section,
                            x.statut,
                            x.mode_expert
                                ? 'mode expert'
                                : null,
                            x.content_origin !== "base"
                                ? x.content_origin_label
                                : null
                        ].filter(Boolean).join(" • "))}</span>${x.raison ? `<span class="itemMeta">${esc(x.raison)}</span>` : ""}</span><span class="coords">${x.x != null ? `X ${x.x.toFixed(0)} · Z ${x.z.toFixed(0)}` : ""}</span></button>${x.x != null ? BOTWI18n.t("renderitems", {value6: String(planned.has(itemId(x)) ? '✓' : '+'), value7: String(`</button>`), value10: String(`<button type="button" class="routeAdd ${planned.has(itemId(x)) ? 'active' : ''}" data-route-add="${esc(itemId(x))}" aria-label="${BOTWI18n.t("renderitems-the-route-2", {value2: String(planned.has(itemId(x)) ? BOTWI18n.t("renderitems-remove", {}) : BOTWI18n.t("renderitems-add", {})),value3: String(esc(x.name || x.display_name || x.id)),value4: String(planned.has(itemId(x)) ? BOTWI18n.t("renderitems-of", {}) : BOTWI18n.t("renderitems-at", {}))})}" title="${BOTWI18n.t("renderitems-the-route", {value5: String(planned.has(itemId(x)) ? BOTWI18n.t("renderitems-remove-from", {}) : BOTWI18n.t("renderitems-add-to", {}))})}">`)}) : ""}</div>`
                )
                .join("") +

                (
                    more
                        ? BOTWI18n.t("renderitems-show-more-results-remaining", {value0: String(Math.min(LIST_PAGE_SIZE, more)), value1: String(more.toLocaleString(BOTWI18n.formatLocale)), value2: String(more > 1 ? 's' : ''), value3: String(`</button>`), value4: String(`<button id="showMoreResults" class="showMoreResults">`), count: more})
                        : ""
                )
            : BOTWI18n.t("renderitems-no-items-with-these-filters", {value0: String(`</div>`), value1: String(`<div class="empty">`)});

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
            ? BOTWI18n.t("renderfilterscopenotice-all-modes-are-displayed-placement-exclusive-to", {value0: String(expert.toLocaleString(BOTWI18n.formatLocale)), value1: String(expert > 1 ? 's' : ''), value2: String(expert > 1 ? 's' : ''), count: expert})
            : mode === "normal"
                ? BOTWI18n.t("renderfilterscopenotice-placements-exclusive-to-master-mode-are-hidden", {})
                : mode === "expert"
                    ? BOTWI18n.t("renderfilterscopenotice-common-placements-and-placements-exclusive-to-master", {})
                    : "";

    $("#filterScopeNotice").innerHTML =
        BOTWI18n.t("renderfilterscopenotice-verified-coverage-on-hyrule-on-interior-maps", {value0: String(esc(warning)), value1: String(map.toLocaleString(BOTWI18n.formatLocale)), value2: String(interior.toLocaleString(BOTWI18n.formatLocale)), value3: String(list.toLocaleString(BOTWI18n.formatLocale)), value4: String(audit.status && audit.status !== "complete" ? BOTWI18n.t("renderfilterscopenotice-the-reference-counters-require-verification", {value0: String(`</strong>`), value1: String(`<strong>`)}) : ''), value5: String(`</span>`), value6: String(`<span>`), value7: String(`</b>`), value8: String(`<b>`)});
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
        BOTWI18n.t("select-loading-details-details-are-retrieved-locally-on", {value0: String(`</div>`), value1: String(`</small>`), value2: String(`<small>`), value3: String(`</b>`), value4: String(`<b id="detailTitle">`), value5: String(`<div class="detailLoading">`)});

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
                    BOTWI18n.t("select-details-unavailable", {})
                );
            }

            if (
                payload.report_revision_key !==
                report.report_revision_key
            ) {
                throw Error(
                    BOTWI18n.t("select-this-sheet-belongs-to-another-revision-of", {})
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
                return `<span aria-hidden="true" title="${esc(x.name)}" data-map-id="${esc(id)}" class="marker baseMapMarker ${stateClass(x)} ${selectedId === id ? 'selected' : ''}" style="left:${p.x / MAP_W * 100}%;top:${p.y / MAP_H * 100}%"></span>`
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

            return BOTWI18n.t("rendermap", {value6: String(group.length), value7: String(`</button>`), value10: String(`<button type="button" title="${BOTWI18n.t("rendermap-zoom-to-items-2", {value0: String(group.length)})}" aria-label="${BOTWI18n.t("rendermap-zoom-to-items", {value1: String(group.length)})}" data-cluster-x="${p.x}" data-cluster-y="${p.y}" class="marker cluster" style="left:${p.x / MAP_W * 100}%;top:${p.y / MAP_H * 100}%">`)});
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

                return BOTWI18n.t("rendermap-2", {value6: String(index + 1), value7: String(`</button>`), value9: String(`<button type="button" title="${esc(point.label)}" aria-label="${BOTWI18n.t("rendermap-step", {value1: String(index + 1),value2: String(esc(point.label))})}" data-route-index="${index}" class="marker waypoint" style="left:${p.x / MAP_W * 100}%;top:${p.y / MAP_H * 100}%">`)})
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

                return BOTWI18n.t("rendermap-3", {value8: String(index + 1), value9: String(`</button>`), value12: String(`<button type="button" title="${BOTWI18n.t("rendermap-step-2", {value0: String(index + 1),value1: String(esc(point.name))})}" aria-label="${BOTWI18n.t("rendermap-planned-step", {value2: String(index + 1),value3: String(esc(point.name))})}" data-planner-index="${index}" class="marker plannerWaypoint ${point.locked ? 'locked' : ''}" style="left:${p.x / MAP_W * 100}%;top:${p.y / MAP_H * 100}%">`)})
            }
        ).join("");

    const startMarker =
        start
            ? (() => {
                const p =
                    worldPoint(start);

                return BOTWI18n.t("rendermap-d", {value4: String(`</button>`), value7: String(`<button type="button" title="${BOTWI18n.t("rendermap-start", {value0: String(esc(start.label || BOTWI18n.t("rendermap-custom-point", {})))})}" aria-label="${BOTWI18n.t("rendermap-starting-point", {value1: String(esc(start.label || BOTWI18n.t("rendermap-custom-point-2", {})))})}" class="marker routeStart" style="left:${p.x / MAP_W * 100}%;top:${p.y / MAP_H * 100}%">`)})
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
            ? BOTWI18n.t("helpfor-the-marker-is-placed-at-coordinates-x", {value0: String(x.x.toFixed(1)), value1: String(x.z.toFixed(1))})
            : BOTWI18n.t("helpfor-this-objective-does-not-yet-have-reliable", {});

    if (x.farm) {
        return BOTWI18n.t("helpfor-this-farm-point-is-always-displayed-the", {value0: String(coord), value1: String(x.scalable ? BOTWI18n.t("helpfor-its-family-and-location-are-reliable-but", {}) : BOTWI18n.t("helpfor-the-static-variant-shown-comes-from-the", {}))});
    }

    const guide = {
        sanctuaires:
            BOTWI18n.t("helpfor-activate-the-travel-point-complete-the-trial", {value0: String(coord), value1: String(x.trial ? ` « ${x.trial} »` : ""), value2: String(x.quest ? BOTWI18n.t("helpfor-access-depends-on-the-quest", {value0: String(x.quest)}) : "")}),

        coffres_sanctuaires:
            BOTWI18n.t("helpfor-return-to-this-shrine-and-check-every", {value0: String(coord), value1: String(x.raison || BOTWI18n.t("helpfor-the-chest-is-not-marked-as-opened", {}))}),

        coffres_monde:
            BOTWI18n.t("helpfor-this-chest-has-a-permanent-flag-opening", {value0: String(coord), value1: String(x.contenu ? BOTWI18n.t("helpfor-identified-content", {value0: String(x.contenu)}) : "")}),

        coffres_donjons:
            BOTWI18n.t("helpfor-explore-the-area-before-leaving-this-chest", {value0: String(x.secteur || BOTWI18n.t("helpfor-the-dungeon", {}))}),

        korogus:
            BOTWI18n.t("helpfor-look-for-a-small-environmental-puzzle-near", {value0: String(coord)}),

        tours:
            BOTWI18n.t("helpfor-reach-the-top-and-examine-the-sheikah", {value0: String(coord)}),

        lieux:
            BOTWI18n.t("helpfor-walk-through-this-area-until-its-name", {value0: String(coord)}),

        quetes_sanctuaires:
            BOTWI18n.t("helpfor-this-first-marker-is-the-start-of", {value0: String(coord), value1: String(x.sanctuaire ? `« ${x.sanctuaire} »` : BOTWI18n.t("helpfor-the-shrine", {}))}),

        quetes_principales:
            BOTWI18n.t("helpfor-start-at-the-first-marker-then-check", {value0: String(coord)}),

        quetes_secondaires:
            BOTWI18n.t("helpfor-the-first-marker-shows-where-to-start", {value0: String(coord), value1: String(x.statut), value2: String(x.region ? BOTWI18n.t("helpfor-in-the-region", {value0: String(x.region)}) : "")}),

        souvenirs:
            BOTWI18n.t("helpfor-reach-the-marker-and-then-trigger-the", {value0: String(coord)}),

        hinox:
            BOTWI18n.t("helpfor-defeat-this-hinox-then-save-your-game", {value0: String(coord)}),

        talus:
            BOTWI18n.t("helpfor-defeat-this-stone-talus-then-save-your", {value0: String(coord)}),

        moldarquors:
            BOTWI18n.t("helpfor-lure-the-molduga-with-a-bomb-on", {value0: String(coord)}),

        compendium:
            BOTWI18n.t("helpfor-photograph-with-the-camera-rune-until-it", {value0: String(x.name)}),

        armures:
            BOTWI18n.t("helpfor-obtain-at-least-once-ownership-and-its", {value0: String(x.name), value1: String(x.etoiles || "☆☆☆☆")}),

        armures_max:
            x.possede
                ? BOTWI18n.t("helpfor-upgrade-at-a-great-fairy-fountain-to", {value0: String(x.name), value1: String(x.niveau), value2: String(x.etoiles)})
                : BOTWI18n.t("helpfor-first-obtain-then-upgrade-it-four-times", {value0: String(x.name)}),
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
        return BOTWI18n.t("frenchsourcename-zelda-wiki-article-about", {value0: String(itemName)});
    }

    const exact = {
        "BOTW Event Flow Viewer - flux de quête":
            BOTWI18n.t("frenchsourcename-viewer-of-botw-event-flows", {}),
        "BOTW Object Map":
            BOTWI18n.t("frenchsourcename-map-of-botw-objects-objmap", {}),
        "Zelda Dungeon Interactive Map":
            BOTWI18n.t("frenchsourcename-zelda-dungeon-interactive-map", {}),
        "Zelda Dungeon - Leviathan Bones":
            BOTWI18n.t("frenchsourcename-zelda-dungeon-article-on-whale-fossils", {}),
        "Zelda Dungeon - Sunken Treasure":
            BOTWI18n.t("frenchsourcename-zelda-dungeon-article-on-the-sunken-treasures", {}),
        "Zelda Dungeon - Épreuves de l'Épée":
            BOTWI18n.t("frenchsourcename-zelda-dungeon-trials-of-the-sword", {})
    };

    return exact[name] || name;
}

function guideSources(sources, itemName) {
    if (!sources?.length) {
        return "";
    }

    return BOTWI18n.t("guidesources-reference-sources", {value0: String(sources.map(source => `<a href="${esc(source.url)}" target="_blank" rel="noreferrer">${esc(frenchSourceName(source.name, itemName))} ↗</a>`).join("")), value1: String(`</div>`), value2: String(`</small>`), value3: String(`<small>`), value4: String(`<div class="guideSources">`)});
}

function renderDetails(x) {
    const category =
        report.categories[x.categorie]?.label ||
        x.filter_label ||
        BOTWI18n.t("renderdetails-map-information", {});

    const displayLabels = {
        map_and_list:
            BOTWI18n.t("renderdetails-hyrule-map-and-list", {}),
        interior_only:
            BOTWI18n.t("renderdetails-internal-map-and-list", {}),
        list_only:
            BOTWI18n.t("renderdetails-list-only", {})
    };

    const facts = [
        [BOTWI18n.t("renderdetails-region", {}), x.region],
        [BOTWI18n.t("renderdetails-origin", {}), x.content_origin_label],
        [BOTWI18n.t("renderdetails-position", {}), x.placement_label],
        [BOTWI18n.t("renderdetails-coverage", {}), x.coverage_label],
        [BOTWI18n.t("renderdetails-display", {}), displayLabels[x.display_scope]],
        [BOTWI18n.t("renderdetails-location", {}), x.location_status_label],
        [BOTWI18n.t("ui-mode", {}), x.game_mode_label],
        [BOTWI18n.t("renderdetails-activity", {}), x.activity_scope_label],
        [BOTWI18n.t("renderdetails-initial-variant", {}), x.subtype],
        [BOTWI18n.t("renderdetails-reward", {}), x.reward],
        [
            BOTWI18n.t("renderdetails-farm-blood-moon", {}),
            x.farm
                ? BOTWI18n.t("renderdetails-always-displayed", {})
                : null
        ],
        [
            BOTWI18n.t("renderdetails-developments", {}),
            x.scalable
                ? BOTWI18n.t("renderdetails-variant-that-may-change", {})
                : null
        ],
        [BOTWI18n.t("renderdetails-nearby-location", {}), x.nearby],
        [BOTWI18n.t("renderdetails-test", {}), x.trial],
        [BOTWI18n.t("renderdetails-linked-quest", {}), x.quest],
        [BOTWI18n.t("renderdetails-shrine", {}), x.sanctuaire],
        [BOTWI18n.t("renderdetails-contents", {}), x.contenu],
        [BOTWI18n.t("renderdetails-sector", {}), x.secteur || x.section],
        [BOTWI18n.t("renderdetails-set", {}), x.set],
        [
            BOTWI18n.t("renderdetails-level", {}),
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
            ? BOTWI18n.t("renderdetails-materials-to-reach", {value0: String("★".repeat(upgrade.niveau_cible)), value1: String(upgrade.materiaux.map(m => `<div class="recipeRow ${m.disponible ? 'ready' : 'missing'}"><span>${esc(m.name)}</span><b>${m.possede} / ${m.requis}</b><small>${m.manque ? BOTWI18n.t("renderdetails-missing", {value0: String(m.manque)}) : BOTWI18n.t("renderdetails-ready", {})}</small></div>`).join("")), value2: String(`</div>`), value3: String(`</div>`), value4: String(`<div class="recipe">`), value5: String(`</h3>`), value6: String(`<h3>`), value7: String(`<div class="detailSection">`)})
            : "";

    const geo =
        x.geo_points || [];

    const geoBlock =
        geo.length
            ? `<div class="detailSection"><h3>${geo.length > 1 ? BOTWI18n.t("renderdetails-steps-and-locations", {}) : BOTWI18n.t("renderdetails-location-2", {})}</h3><div class="geoPoints">${geo.map((p, i) => BOTWI18n.t("renderdetails-x-z-map-copy-objmap", {value0: String(esc(p.label)), value1: String(esc(p.nearby ? BOTWI18n.t("renderdetails-near", {value0: String(p.nearby), value1: String(p.nearby_distance_m != null ? BOTWI18n.t("renderdetails-approximately-m", {value0: String(p.nearby_distance_m)}) : "")}) : BOTWI18n.t("renderdetails-world-coordinates", {}))), value2: String(Number(p.x).toFixed(2)), value3: String(Number(p.z).toFixed(2)), value8: String(`</article>`), value9: String(`</div>`), value10: String(`</a>`), value11: String(`<a href="https://objmap.zeldamods.org/#/map/z6,${p.x},${p.z}" target="_blank" rel="noreferrer">`), value12: String(`</button>`), value13: String(`<button data-geo-copy="${i}">`), value14: String(`</button>`), value15: String(`<button data-geo-center="${i}">`), value16: String(`<div class="geoActions">`), value17: String(`</div>`), value18: String(`</span>`), value19: String(`<span>`), value20: String(`</small>`), value21: String(`<small>`), value22: String(`</b>`), value23: String(`<b>`), value24: String(`<div>`), value25: String(`<article class="geoPoint">`)})).join("")}</div></div>`
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
            ? BOTWI18n.t("renderdetails-physical-chest-recorded-in-the-game-data", {value0: String(esc(x.interior_map_label || BOTWI18n.t("renderdetails-interior-map", {}))), value1: String(interiorPoints.length), value2: String(interiorPoints.length > 1 ? 's' : ''), value3: String(interiorPoints.length > 1 ? 's' : ''), value4: String(interiorPoints.length > 1 ? 's' : ''), value5: String(interiorPoints.map((p, i) => { const detail = guide?.chest_details?.[i] || p; return `<article><span>${detail.number || i + 1}</span><div><b>${esc(p.content || x.contenu || BOTWI18n.t("renderdetails-treasure-chest", {}))}</b>${detail.area ? `<small>${esc(detail.area)}</small>` : `<small>X ${Number(p.x).toFixed(2)} • Y ${Number(p.y).toFixed(2)} • Z ${Number(p.z).toFixed(2)}</small>`}${detail.access_label ? `<em>${esc(detail.access_label)}</em>` : ""}${detail.access ? `<p>${esc(detail.access)}</p>` : ""}</div></article>`; }).join("")), value6: String(esc(x.interior_map)), value7: String(`</div>`), value8: String(`</small>`), value9: String(`<small class="interiorNote">`), value10: String(`</div>`), value11: String(`<div class="interiorPoints">`), value12: String(`</p>`), value13: String(`<p>`), value14: String(`</h3>`), value15: String(`<h3>`), value16: String(`<div class="detailSection interiorCard">`), count: interiorPoints.length})
            : "";

    const stateLabels = {
        termine: BOTWI18n.t("renderdetails-completed", {}),
        actuel: BOTWI18n.t("renderdetails-current-stage", {}),
        a_faire: BOTWI18n.t("renderdetails-to-do", {}),
        a_verifier: BOTWI18n.t("renderdetails-to-be-checked", {}),
        verrouille: BOTWI18n.t("renderdetails-after-activation", {})
    };

    const qualityBlock =
        guide?.quality_label
            ? `<div class="guideQuality quality${guide.quality_level}"><b>${esc(guide.quality_label)}</b><small>${esc(guide.verification_basis)}</small></div>`
            : "";

    const evidenceBlock =
        guide?.quest_evidence
            ? BOTWI18n.t("renderdetails-proof-of-the-quest-flow-nodes-actions", {value0: String(guide.quest_evidence.event_nodes), value1: String(guide.quest_evidence.event_actions), value2: String(guide.quest_evidence.message_references), value3: String(`</div>`), value4: String(`</p>`), value5: String(`<p>`), value6: String(`</small>`), value7: String(`<small>`), value8: String(`<div class="guideEvidence">`)})
            : "";

    const trialBlock =
        guide?.trial_rooms?.length
            ? BOTWI18n.t("renderdetails-rooms-at-this-level", {value0: String(guide.trial_rooms.map(room => `<article class="trialRoom ${esc(room.kind)}"><span>${room.floor}</span><div><small>${esc(room.kind_label)}</small><b>${esc(room.enemies)}</b><p>${esc(room.strategy)}</p></div></article>`).join("")), value1: String(`</div>`), value2: String(`</h3>`), value3: String(`<h3>`), value4: String(`<div class="trialRooms">`)})
            : "";

    const bossBlock =
        guide?.boss_profile
            ? BOTWI18n.t("renderdetails-combat-profile-weak-point", {value0: String(esc(guide.boss_profile.variant)), value1: String(esc(guide.boss_profile.weak_point)), value2: String(guide.boss_profile.scaling ? `<p>${esc(guide.boss_profile.scaling)}</p>` : ""), value3: String(`</div>`), value4: String(`</p>`), value5: String(`</strong>`), value6: String(`<strong>`), value7: String(`<p>`), value8: String(`</b>`), value9: String(`<b>`), value10: String(`</small>`), value11: String(`<small>`), value12: String(`<div class="guideBoss">`)})
            : "";

    const guideBlock =
        guide
            ? BOTWI18n.t("renderdetails-objective-guide-next-action", {value0: String(guide.specificity_label ? `<span>${esc(guide.specificity_label)}</span>` : ""), value1: String(qualityBlock), value2: String(esc(guide.summary)), value3: String(guide.mechanic ? BOTWI18n.t("renderdetails-mechanic", {value0: String(esc(guide.mechanic)), value1: String(`</div>`), value2: String(`</b>`), value3: String(`<b>`), value4: String(`</small>`), value5: String(`<small>`), value6: String(`<div class="guideMechanic">`)}) : ""), value4: String(bossBlock), value5: String(esc(guide.current_action)), value6: String(guideList(BOTWI18n.t("renderdetails-prerequisite", {}), guide.prerequisites)), value7: String(guideList(BOTWI18n.t("renderdetails-preparation", {}), guide.preparation)), value8: String(evidenceBlock), value9: String(trialBlock), value10: String(guide?.trial_rooms?.length ? "" : guideList(BOTWI18n.t("renderdetails-detailed-solution", {}), guide.detailed_steps, true, "solution")), value11: String(guide.chest_solution ? BOTWI18n.t("renderdetails-shrine-chest", {value0: String(esc(guide.chest_solution)), value1: String(`</div>`), value2: String(`</p>`), value3: String(`<p>`), value4: String(`</small>`), value5: String(`<small>`), value6: String(`<div class="guideChest">`)}) : ""), value12: String(guideList(BOTWI18n.t("renderdetails-rewards", {}), guide.rewards, false, "rewards")), value13: String((guide.steps || []).map((s, i) => `<article class="guideStep ${esc(s.state)}"><span>${i + 1}</span><div><b>${esc(s.title)}</b><p>${esc(s.instruction)}</p><small>${esc(stateLabels[s.state] || s.state)}</small></div>${s.geo_point_index != null && geo[s.geo_point_index] ? BOTWI18n.t("renderdetails-map", {value1: String(`</button>`), value2: String(`<button data-guide-center="${s.geo_point_index}">`)}) : ""}</article>`).join("")), value14: String(guideList(BOTWI18n.t("renderdetails-tips", {}), guide.tips, false, "tips")), value15: String(guideList(BOTWI18n.t("renderdetails-notes", {}), guide.warnings, false, "warnings")), value16: String(guide.completion.automatic === false ? BOTWI18n.t("renderdetails-tracking", {}) : BOTWI18n.t("renderdetails-automatic-completion", {})), value17: String(esc(guide.completion.condition)), value18: String(guideSources(guide.sources, x.name || BOTWI18n.t("renderdetails-this-objective", {}))), value19: String(`</div>`), value20: String(`</div>`), value21: String(`</p>`), value22: String(`<p>`), value23: String(`</small>`), value24: String(`<small>`), value25: String(`<div class="completionProof">`), value26: String(`</div>`), value27: String(`<div class="guideSteps">`), value28: String(`</div>`), value29: String(`</b>`), value30: String(`<b>`), value31: String(`</small>`), value32: String(`<small>`), value33: String(`<div class="currentAction">`), value34: String(`</p>`), value35: String(`<p class="guideSummary">`), value36: String(`</div>`), value37: String(`</h3>`), value38: String(`<h3>`), value39: String(`<div class="guideTitle">`), value40: String(`<div class="detailSection guideCard">`)})
            : BOTWI18n.t("renderdetails-how-to-finish-it", {value0: String(esc(helpFor(x))), value1: String(`</div>`), value2: String(`</p>`), value3: String(`<p>`), value4: String(`</h3>`), value5: String(`<h3>`), value6: String(`<div class="detailSection">`)});

    const manual =
        manualEntry(x),
        farmWarning =
            x.farm
                ? BOTWI18n.t("renderdetails-this-state-never-removes-this-farm-point", {})
                : BOTWI18n.t("renderdetails-the-validation-remains-after-a-new-analysis", {});

    const scopeBlock =
        x.coverage_note
            ? BOTWI18n.t("renderdetails-limit-of-coverage", {value0: String(esc(x.coverage_note)), value1: String(`</div>`), value2: String(`</p>`), value3: String(`<p>`), value4: String(`</h3>`), value5: String(`<h3>`), value6: String(`<div class="detailSection scopeWarning">`)})
            : "";

    const manualBlock =
        BOTWI18n.t("renderdetails-persistent-manual-tracking-save-personal-mark-this", {value0: String(x.termine ? BOTWI18n.t("renderdetails-validated-automatically", {}) : BOTWI18n.t("renderdetails-not-automatically-validated", {})), value1: String(manual.completed ? BOTWI18n.t("renderdetails-validated-manually", {}) : BOTWI18n.t("renderdetails-not-checked", {})), value3: String(esc(manual.note || "")), value4: String(esc(farmWarning)), value5: String(`</div>`), value6: String(`</p>`), value7: String(`<p class="manualHint">`), value8: String(`</button>`), value9: String(`<button id="saveManualNote">`), value10: String(`</label>`), value11: String(`</textarea>`), value13: String(`<textarea id="manualNoteInput" maxlength="1000" placeholder="${BOTWI18n.t("renderdetails-optional-personal-best-checked-chest-next-action", {})}">`), value14: String(`<label class="manualNoteLabel">`), value15: String(`</label>`), value16: String(`</span>`), value17: String(`<span>`), value18: String(`<input id="manualComplete" type="checkbox" ${manual.completed ? 'checked' : ''}>`), value19: String(`<label class="manualCheck">`), value20: String(`</div>`), value21: String(`</span>`), value22: String(`</b>`), value23: String(`<b>`), value24: String(`</small>`), value25: String(`<small>`), value26: String(`<span>`), value27: String(`</span>`), value28: String(`</b>`), value29: String(`<b>`), value30: String(`</small>`), value31: String(`<small>`), value32: String(`<span>`), value33: String(`<div class="statusSplit">`), value34: String(`</h3>`), value35: String(`<h3>`), value36: String(`<div class="detailSection manualTracking">`)});

    const inRoute =
        routeIds().has(itemId(x));

    $("#detailContent").innerHTML =
        BOTWI18n.t("renderdetails-find-a-guide", {value0: String(esc(category)), value1: String(esc(x.name || x.id)), value2: String(esc([x.region, x.dlc ? "DLC" : null].filter(Boolean).join(" • "))), value4: String(esc(trackingLabel(x))), value5: String(facts.length ? `<div class="detailFacts">${facts.map(([k, v]) => `<div class="detailFact"><small>${esc(k)}</small>${esc(v)}</div>`).join("")}</div>` : ""), value6: String(scopeBlock), value7: String(manualBlock), value8: String(guideBlock), value9: String(geoBlock), value10: String(interiorBlock), value11: String(recipe), value12: String(coords && !geo.length ? BOTWI18n.t("renderdetails-botw-coordinates-x-z", {value0: String(x.x.toFixed(2)), value1: String(x.z.toFixed(2)), value2: String(`</div>`), value3: String(`</p>`), value4: String(`<p>`), value5: String(`</h3>`), value6: String(`<h3>`), value7: String(`<div class="detailSection">`)}) : ""), value13: String(coords ? BOTWI18n.t("renderdetails-the-route-center-on-the-map-copy", {value0: String(inRoute ? BOTWI18n.t("renderdetails-remove-from", {}) : BOTWI18n.t("renderdetails-add-to", {})), value2: String(`</a>`), value3: String(`<a href="${objmap}" target="_blank" rel="noreferrer">`), value4: String(`</button>`), value5: String(`<button id="copyCoords">`), value6: String(`</button>`), value7: String(`<button id="detailCenter">`), value8: String(`</button>`), value9: String(`<button id="detailRoute">`)}) : ""), value15: String(`</div>`), value16: String(`</a>`), value17: String(`<a href="${search}" target="_blank" rel="noreferrer">`), value18: String(`<div class="detailActions">`), value19: String(`</span>`), value20: String(`</i>`), value21: String(`<i class="dot ${stateClass(x)}" aria-hidden="true">`), value22: String(`<span class="detailStatus">`), value23: String(`</p>`), value24: String(`<p class="detailMeta">`), value25: String(`</h2>`), value26: String(`<h2 id="detailTitle">`), value27: String(`</p>`), value28: String(`<p class="detailEyebrow">`)});

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
                    BOTWI18n.t("renderdetails-coordinates-copied", {})
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
                            BOTWI18n.t("renderdetails-coordinates-copied-2", {})
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
        BOTWI18n.t("rendermanualsummary-completed-objective", {value0: String(completed.toLocaleString(BOTWI18n.formatLocale)), value1: String(completed === 1 ? '' : 's'), value2: String(completed === 1 ? '' : 's'), count: completed});

    $("#manualNote").textContent =
        BOTWI18n.t("rendermanualsummary-note-revision-separate-from-the-automatic-score", {value0: String(notes), value1: String(notes === 1 ? '' : 's'), value2: String(manualTracking.revision), count: notes});

    $("#toggleManualReview").textContent =
        BOTWI18n.t("ui-validations", {value0: String(completed.toLocaleString(BOTWI18n.formatLocale))});

    renderManualReview();
}

function manualSearchText(value) {
    return String(value || "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLocaleLowerCase(BOTWI18n.formatLocale);
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

            return byDate || left.name.localeCompare(right.name, BOTWI18n.formatLocale);
        });
}

function manualDate(value) {
    if (!value) {
        return BOTWI18n.t("manualdate-unknown-date", {});
    }

    const date = new Date(value);

    return Number.isNaN(date.getTime())
        ? BOTWI18n.t("manualdate-unknown-date-2", {})
        : date.toLocaleString(BOTWI18n.formatLocale, {
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
        ).entries()].sort((left, right) => left[1].localeCompare(right[1], BOTWI18n.formatLocale));

    categorySelect.innerHTML =
        BOTWI18n.t("rendermanualreview-all-categories", {value0: String(`</option>`), value1: String(`<option value="all">`)}) +
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
        ? BOTWI18n.t("rendermanualreview-manual-completion-displayed", {value0: String(records.length.toLocaleString(BOTWI18n.formatLocale)), value1: String(records.length === 1 ? '' : 's'), value2: String(records.length === 1 ? '' : 's'), value3: String(filtered.length.toLocaleString(BOTWI18n.formatLocale)), value4: String(filtered.length === 1 ? '' : 's'), count: records.length, count2: filtered.length})
        : BOTWI18n.t("rendermanualreview-no-lens-manually-checked", {});

    if (!filtered.length) {
        list.innerHTML = `<div class="manualReviewEmpty">${records.length ? BOTWI18n.t("rendermanualreview-no-validation-matches-this-search", {}) : BOTWI18n.t("rendermanualreview-manually-completed-objectives-will-appear-here", {})}</div>`;
        return;
    }

    list.innerHTML = filtered.map(record => {
        const status = record.item
            ? record.automatic
                ? BOTWI18n.t("rendermanualreview-also-automatically-validated", {})
                : BOTWI18n.t("rendermanualreview-not-automatically-validated", {})
            : BOTWI18n.t("rendermanualreview-missing-from-the-current-catalogue", {}),
            meta = [
                record.region,
                status,
                manualDate(record.entry.updated_at)
            ].filter(Boolean).join(" • "),
            note = record.entry.note
                ? `<p class="manualReviewNote">Note : ${esc(record.entry.note)}</p>`
                : "";

        return BOTWI18n.t("rendermanualreview-open-details-completed", {value0: String(esc(record.categoryLabel)), value1: String(esc(record.name)), value2: String(esc(meta)), value3: String(note), value7: String(`</article>`), value8: String(`</div>`), value9: String(`</label>`), value10: String(`<input type="checkbox" checked data-manual-uncheck="${esc(record.trackingId)}">`), value11: String(`<label class="manualReviewToggle">`), value12: String(`</button>`), value13: String(`<button type="button" data-manual-open="${esc(record.trackingId)}"${record.item ? "" : " disabled"}>`), value14: String(`<div class="manualReviewItemActions">`), value15: String(`</div>`), value16: String(`</p>`), value17: String(`<p>`), value18: String(`</h3>`), value19: String(`<h3>`), value20: String(`</span>`), value21: String(`<span class="manualReviewCategory">`), value22: String(`<div>`), value23: String(`<article class="manualReviewItem">`)});
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
        BOTWI18n.t("uncheckmanualfromreview-clear-the-manual-completion-of-your-personal", {value0: String(record.name)})
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
                BOTWI18n.t("savemanualbyid-saving-failed", {})
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
                ? BOTWI18n.t("savemanualbyid-manual-validation-registered", {})
                : BOTWI18n.t("savemanualbyid-manual-validation-cancelled", {})
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
                    BOTWI18n.t("importmanualfile-restore-failed", {})
                );
            }
            await load(false);
            toast(
                BOTWI18n.t("importmanualfile-restored-tracking-routes-and-preferences", {})
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
                BOTWI18n.t("importmanualfile-import-failed", {})
            );
        }

        manualTracking = data;

        renderAll();

        toast(
            BOTWI18n.t("importmanualfile-imported-and-merged-manual-tracking", {})
        );

    } catch (error) {
        toast(
            error.message ||
            BOTWI18n.t("importmanualfile-invalid-file", {}),
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
                BOTWI18n.t("togglerouteitem-this-element-does-not-have-reliable-coordinates", {}),
                true
            );

            return;
        }

        if (
            routeState.entries.length >=
            ROUTE_LIMIT
        ) {
            toast(
                BOTWI18n.t("togglerouteitem-a-session-is-limited-to-steps", {value0: String(ROUTE_LIMIT)}),
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
            BOTWI18n.t("addfilteredtoroute-no-new-localized-results-to-add", {}),
            true
        );
    } else {
        toast(
            BOTWI18n.t("addfilteredtoroute-step-added", {value0: String(added.length), value1: String(added.length > 1 ? 's' : ''), value2: String(added.length > 1 ? 's' : ''), value3: String(available.length > capacity ? BOTWI18n.t("addfilteredtoroute-limit-of-reached", {value0: String(ROUTE_LIMIT)}) : ''), count: added.length})
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
            BOTWI18n.t("optimizecurrentroute-add-at-least-two-steps", {}),
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
        BOTWI18n.t("optimizecurrentroute-optimized-order-locked-and-unavailable-steps-retained", {})
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
                    BOTWI18n.t("setroutestart-custom-point", {})
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
            ? BOTWI18n.t("renderroute-step", {value0: String(points.length), value1: String(points.length > 1 ? 's' : ''), value2: String(formatDistance(total)), value3: String(missing ? BOTWI18n.t("renderroute-unavailable", {value0: String(missing), value1: String(missing > 1 ? 's' : ''), count: missing}) : ''), count: points.length})
            : BOTWI18n.t("renderroute-no-steps-selected", {});

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
        BOTWI18n.t("renderroute-departure", {value0: String(routeState.start
                ? `${routeState.start.label} - X ${Math.round(routeState.start.x)}, Z ${Math.round(routeState.start.z)}`
                : BOTWI18n.t("renderroute-premier-objective", {}))});

    $("#routeRegions").textContent =
        BOTWI18n.t("renderroute-regions", {value0: String(regions.length
                ? regions.join(", ")
                : "-")});

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
                                BOTWI18n.t("renderroute-unknown-region", {});

                        return BOTWI18n.t("renderroute-2", {value2: String(index + 1), value3: String(esc(name)), value4: String(value.item ? BOTWI18n.t("renderroute-total", {value0: String(esc(region)), value1: String(leg.index === 1 && !routeState.start ? BOTWI18n.t("renderroute-start", {}) : `+ ${formatDistance(leg.distance)}`), value2: String(formatDistance(leg.cumulative))}) : BOTWI18n.t("renderroute-step-unavailable-in-the-current-catalog-its", {})), value5: String(value.item ? BOTWI18n.t("renderroute", {value2: String(`</button>`), value5: String(`<button data-route-focus="${esc(entry.tracking_id)}" title="${BOTWI18n.t("renderroute-view-on-map", {})}" aria-label="${BOTWI18n.t("renderroute-view-on-the-map", {value1: String(esc(name))})}">`)}) : ""), value14: String(entry.locked ? '🔒' : '○'), value17: String(`</article>`), value18: String(`</div>`), value19: String(`</button>`), value22: String(`<button data-route-remove="${esc(entry.tracking_id)}" title="${BOTWI18n.t("renderroute-remove", {})}" aria-label="${BOTWI18n.t("renderroute-remove-from-the-route", {value16: String(esc(name))})}">`), value23: String(`</button>`), value26: String(`<button data-route-lock="${stateIndex}" class="${entry.locked ? 'active' : ''}" title="${BOTWI18n.t("renderroute-lock-this-position", {})}" aria-label="${BOTWI18n.t("renderroute-the-position-of", {value12: String(entry.locked ? BOTWI18n.t("renderroute-unlock", {}) : BOTWI18n.t("renderroute-lock", {})),value13: String(esc(name))})}">`), value27: String(`</button>`), value30: String(`<button data-route-down="${stateIndex}" title="${BOTWI18n.t("renderroute-move-down-2", {})}" aria-label="${BOTWI18n.t("renderroute-move-down", {value9: String(esc(name))})}">`), value31: String(`</button>`), value34: String(`<button data-route-up="${stateIndex}" title="${BOTWI18n.t("renderroute-move-up-2", {})}" aria-label="${BOTWI18n.t("renderroute-move-up", {value7: String(esc(name))})}">`), value35: String(`<div class="routeStepActions">`), value36: String(`</div>`), value37: String(`</small>`), value38: String(`<small>`), value39: String(`</b>`), value40: String(`<b>`), value41: String(`<div>`), value42: String(`</span>`), value43: String(`<span>`), value44: String(`<article class="routeStep ${value.item ? '' : 'unavailable'}" data-route-step="${stateIndex}">`)})
                    }
                )
                .join("")
            : BOTWI18n.t("renderroute-add-goals-from-results-or-a-record", {value0: String(`</div>`), value1: String(`<div class="empty">`)});

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
            BOTWI18n.t("downloadroute-the-route-is-empty", {}),
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

                BOTWI18n.t("downloadroute-departure", {value0: String(payload.start
                        ? `${payload.start.label} (X ${Math.round(payload.start.x)}, Z ${Math.round(payload.start.z)})`
                        : BOTWI18n.t("downloadroute-premier-objective", {}))}),

                BOTWI18n.t("downloadroute-geographic-distance", {value0: String(formatDistance(payload.total_distance_m))}),

                BOTWI18n.t("downloadroute-regions", {value0: String(payload.regions.join(", "))}),

                "",

                ...payload.steps.map(
                    step =>
                        step.available
                            ? `${step.order}. ${step.name} - ${step.region || BOTWI18n.t("downloadroute-region-not-indicated", {})} - X ${Number(step.x).toFixed(0)}, Z ${Number(step.z).toFixed(0)} - +${formatDistance(step.distance_from_previous_m)}${step.locked ? BOTWI18n.t("downloadroute-locked", {}) : ""}`
                            : BOTWI18n.t("downloadroute-unavailable-in-the-current-catalog-retained", {value0: String(step.order), value1: String(step.name), value2: String(step.locked ? BOTWI18n.t("downloadroute-locked-2", {}) : "")})
                ),

                "",

                BOTWI18n.t("downloadroute-indicative-distance-the-strategy-organizes-the-objectives", {})

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
    name = BOTWI18n.t("routesessiontemplate-new-session", {})
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
            BOTWI18n.t("createroutesession-the-planner-is-limited-to-100-sessions", {}),
            true
        );

        return;
    }

    const session =
        routeSessionTemplate(
            copy
                ? BOTWI18n.t("createroutesession-copy", {value0: String(routeState.name)})
                : BOTWI18n.t("createroutesession-new-session", {})
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
            ? BOTWI18n.t("createroutesession-duplicate-session", {})
            : BOTWI18n.t("createroutesession-new-session-created", {})
    );
}

function deleteRouteSession() {
    if (
        Object.keys(
            routesData.sessions
        ).length === 1
    ) {
        toast(
            BOTWI18n.t("deleteroutesession-create-another-session-before-deleting-it", {}),
            true
        );

        return;
    }

    if (
        !confirm(
            BOTWI18n.t("deleteroutesession-permanently-delete-the-session", {value0: String(routeState.name)})
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
                BOTWI18n.t("importroutefile-import-failed", {})
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
            BOTWI18n.t("importroutefile-imported-session-without-removing-existing-routes", {})
        );

    } catch (error) {
        toast(
            error.message ||
            BOTWI18n.t("importroutefile-invalid-route-file", {}),
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
                BOTWI18n.t("app-point-chosen-on-the-map", {})
        });

        routePickStart = false;

        mapEl.classList.remove(
            "pickStart"
        );

        $("#pickRouteStart").classList.remove(
            "active"
        );

        toast(
            BOTWI18n.t("app-defined-starting-point", {})
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
            BOTWI18n.t("app-check-every-seconds", {value0: String(syncInterval)})
        );
    };

$("#pauseSync").onclick =
    () => {
        syncPaused =
            !syncPaused;

        $("#pauseSync").textContent =
            syncPaused
                ? BOTWI18n.t("app-resume", {})
                : BOTWI18n.t("ui-pause", {});

        $("#pauseSync").classList.toggle(
            "active",
            syncPaused
        );

        syncPaused
            ? clearTimeout(syncTimer)
            : checkSync(false);

        if (syncPaused) {
            toast(
                BOTWI18n.t("app-automatic-pause-synchronization", {})
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
            toast(BOTWI18n.t("app-unable-to-cancel-download", {}), true);
        }
    };

$("#retryUpdateDownload").onclick =
    async () => {
        try {
            await updateDownloadAction("retry");
        } catch (_error) {
            toast(BOTWI18n.t("app-unable-to-resume-download", {}), true);
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
                ? BOTWI18n.t("app-click-on-the-map-to-place-the", {})
                : BOTWI18n.t("app-selection-of-the-cancelled-departure", {})
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
                BOTWI18n.t("app-first-open-a-localised-file", {}),
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
            BOTWI18n.t("app-starting-point-set-from-the-open-detail", {})
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
                BOTWI18n.t("app-enter-valid-x-and-z-coordinates", {}),
                true
            );

            return;
        }

        setRouteStart({
            x,
            z,
            label:
                BOTWI18n.t("app-contact-information", {})
        });

        toast(
            BOTWI18n.t("app-applied-start-coordinates", {})
        );
    };

$("#clearRouteStart").onclick =
    () => {
        setRouteStart(null);

        toast(
            BOTWI18n.t("app-the-first-objective-is-used-as-the", {})
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
                BOTWI18n.t("app-the-session-name-cannot-be-empty", {}),
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
            BOTWI18n.t("app-strategy-recorded-for-this-session", {})
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
                BOTWI18n.t("app-empty-all-the-steps-of-this-session", {})
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
                ? BOTWI18n.t("app-hide", {})
                : BOTWI18n.t("app-show", {});

        $("#toggleRoute").setAttribute(
            "aria-expanded",
            String(hidden)
        );
    };

sendHeartbeat();
