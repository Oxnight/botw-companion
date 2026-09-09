const nativeFetch = window.fetch.bind(window);
const launchFragment = new URLSearchParams(window.location.hash.slice(1));
const sessionToken = launchFragment.get("session") ||
    document.querySelector('meta[name="botw-session-token"]')?.content || "";

if (window.location.hash) {
    history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
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
    return nativeFetch(input, { ...options, headers });
};

let report = null, selectedId = null, filtersInitialized = false;
let saveCaptionRevision = null;
const detailCache = new Map();
let manualTracking = { schema_version: 2, revision: 0, updated_at: null, entries: {} };
let preferencesData = { schema_version: 1, revision: 0, updated_at: null, values: {} };
let preferenceSaveQueue = Promise.resolve();
let onboardingShown = false, helpReturnFocus = null;
let helpChapterId = null, tutorialResume = null, tutorialInertState = [];
let tutorialState = null, tutorialPositionFrame = null, tutorialResizeObserver = null;
let detailReturnTarget = null, manualReviewReturnFocus = null;
const SYNC_INTERVAL_KEY = "botw-companion-sync-interval";
const MAP_MODE_KEY = "botw-companion-map-formula";
const PROFILE_KEY = "botw-companion-completion-profile";
const MODE_FILTER_KEY = "botw-companion-game-mode-filter";
const DSU_SOURCE_KEY = "botw-companion-dsu-source";
const UPDATE_DISMISSED_KEY = "botw-companion-update-dismissed";
const TUTORIAL_VERSION = "1";
let syncTimer = null, syncPaused = false, syncInterval = Math.max(5, Number(localStorage.getItem(SYNC_INTERVAL_KEY) || 30));
let heartbeatTimer = null;
let dsuTimer = null, dsuBusy = false;
let updateDownloadTimer = null;
let availableUpdateVersion = null;
let runtimePlatform = {
    label: "Système local",
    native_dsu_engine: "DSU",
    relaunch_hint: "Tu peux fermer cet onglet. Relance BOTW Companion pour redémarrer l’application."
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
        if (manual) toast("La réponse de mise à jour n’est pas valide", true);
        return;
    }
    if (!manual && dismissedUpdateVersion() === data.latest_version) return;
    $("#updateTitle").textContent = data.title || `BOTW Companion ${data.latest_version}`;
    $("#updateVersions").textContent =
        `Version installée : ${data.current_version} • Nouvelle version : ${data.latest_version}`;
    availableUpdateVersion = data.latest_version;
    $("#downloadUpdate").disabled = false;
    $("#downloadUpdate").textContent = "Télécharger la mise à jour";
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
    if (!state || typeof state.status !== "string") return;
    const active = ["checking", "downloading", "verifying"].includes(state.status);
    const progressVisible = state.status !== "inactive";
    const progress = Math.min(100, Math.max(0, Number(state.progress) || 0));
    $("#updateProgress").hidden = !progressVisible;
    $("#updateProgressBar").value = progress;
    $("#cancelUpdateDownload").hidden = !state.can_cancel;
    $("#retryUpdateDownload").hidden = !state.can_retry;
    $("#downloadUpdate").disabled = active || state.status === "ready_to_install";
    if (state.status === "ready_to_install") {
        $("#downloadUpdate").textContent = "Téléchargement vérifié";
    } else if (active) {
        $("#downloadUpdate").textContent = state.status === "verifying" ? "Vérification…" : "Téléchargement…";
    } else {
        $("#downloadUpdate").textContent = "Télécharger la mise à jour";
    }
    const amount = state.bytes_total > 0
        ? `${formatUpdateBytes(state.bytes_received)} sur ${formatUpdateBytes(state.bytes_total)} (${progress.toFixed(1)} %)`
        : "";
    const rate = state.bytes_per_second > 0
        ? ` • ${formatUpdateBytes(state.bytes_per_second)}/s`
        : "";
    $("#updateProgressText").textContent = [state.message, amount].filter(Boolean).join(" ") + rate;
    if (active) scheduleUpdateDownloadPoll();
}

function scheduleUpdateDownloadPoll() {
    clearTimeout(updateDownloadTimer);
    updateDownloadTimer = setTimeout(refreshUpdateDownload, 750);
}

async function refreshUpdateDownload() {
    try {
        const response = await fetch("/api/update/download");
        if (!response.ok) throw Error("service indisponible");
        renderUpdateDownload(await response.json());
    } catch (_error) {
        clearTimeout(updateDownloadTimer);
    }
}

async function updateDownloadAction(action) {
    const response = await fetch(`/api/update/download/${action}`, { method: "POST" });
    const state = await response.json();
    if (!response.ok) throw Error(state.erreur || "service indisponible");
    renderUpdateDownload(state);
    scheduleUpdateDownloadPoll();
}

async function startUpdateDownload() {
    try {
        await updateDownloadAction("start");
    } catch (_error) {
        toast("Le téléchargement ne peut pas démarrer pour le moment", true);
    }
}

async function checkForUpdates(manual = false) {
    const button = $("#checkUpdates");
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 5000);
    if (manual) {
        button.disabled = true;
        button.textContent = "Vérification…";
    }
    try {
        const response = await fetch(`/api/update${manual ? "?force=1" : ""}`, {
            signal: controller.signal
        });
        if (!response.ok) throw Error("service indisponible");
        const data = await response.json();
        if (data.update_available === true) {
            showAvailableUpdate(data, manual);
        } else if (manual && data.status === "up_to_date") {
            toast("BOTW Companion est à jour");
        } else if (manual && data.status === "unsupported") {
            toast("La vérification automatique n’est pas disponible sur ce système", true);
        } else if (manual) {
            toast(data.message || "Vérification impossible pour le moment", true);
        }
    } catch (_error) {
        if (manual) {
            toast("Connexion indisponible. BOTW Companion reste utilisable hors ligne.", true);
        }
    } finally {
        clearTimeout(timer);
        if (manual) {
            button.disabled = false;
            button.textContent = "Vérifier les mises à jour";
        }
    }
}

function loadRouteState() {
    try {
        const value = JSON.parse(localStorage.getItem(ROUTE_STORAGE_KEY) || "null");

        if (value?.schema_version === 1 && Array.isArray(value.entries)) {
            return value;
        }
    } catch (_error) {
    }

    return {
        schema_version: 1,
        name: "Session BOTW",
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
        localStorage.getItem(localKey) ?? fallback;
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
                throw Error(data.erreur || "Préférences impossibles à enregistrer");
            }
            preferencesData = data;
        })
        .catch(error => toast(error.message, true));
    return preferenceSaveQueue;
}

const HELP_CHAPTERS = [
    {
        id: "privacy",
        title: "Confidentialité et mode hors ligne",
        summary: "Ce qui reste sur ton appareil et ce qui nécessite Internet.",
        target: "header",
        points: [
            "L’analyse de la sauvegarde, la carte, les guides, le suivi manuel et les itinéraires fonctionnent localement.",
            "La sauvegarde et les données personnelles du Companion ne sont envoyées à aucun service distant.",
            "Une connexion est utilisée uniquement lorsque tu demandes une vérification de mise à jour ou ouvres une source externe. Une panne de réseau ne bloque pas le Companion."
        ],
        tip: "Les services locaux du Companion écoutent seulement sur 127.0.0.1, c’est-à-dire ton propre ordinateur."
    },
    {
        id: "save",
        title: "Sauvegarde et slot analysé",
        summary: "Comprendre la détection de Ryujinx ou Cemu et le choix du slot.",
        target: "#savePreview",
        points: [
            "Le bandeau supérieur indique l’émulateur détecté, la plateforme et le slot actuellement conservé.",
            "BOTW Companion compare les sauvegardes prises en charge et retient la progression la plus récente d’après les informations internes du jeu.",
            "L’aperçu, la date et la source permettent de vérifier que tu consultes bien la partie attendue. Une écriture incomplète n’écrase jamais le dernier rapport valide."
        ],
        tip: "Si la mauvaise partie apparaît, vérifie le chemin de sauvegarde de l’émulateur puis utilise « Lire maintenant »."
    },
    {
        id: "sync",
        title: "Synchronisation de la sauvegarde",
        summary: "Intervalle, pause, lecture immédiate et historique.",
        target: ".syncSaveArea",
        points: [
            "Choisis l’intervalle auquel le Companion vérifie si la sauvegarde a réellement changé.",
            "« Pause » suspend les lectures automatiques sans arrêter l’application. « Lire maintenant » déclenche une vérification immédiate.",
            "L’historique récent distingue une lecture réussie, une sauvegarde inchangée et une erreur temporaire. Le dernier résultat valide reste affiché en cas d’échec."
        ],
        tip: "Une vérification fréquente n’accélère pas l’écriture de l’émulateur ; 30 secondes convient dans la plupart des cas."
    },
    {
        id: "completion",
        title: "Les deux pourcentages",
        summary: "Distinguer la carte officielle du profil de complétion.",
        target: ".hero",
        points: [
            "Le pourcentage officiel reproduit le compteur de carte de BOTW : Korogus, sanctuaires, lieux, tours, créatures cartographiques et contenu DLC applicable.",
            "Le profil de complétion est un indicateur plus large propre au Companion. Il mesure les objectifs que la sauvegarde permet de confirmer automatiquement.",
            "Les deux nombres n’ont donc ni le même total ni le même rôle. Le sélecteur de formule ou de profil permet d’examiner le jeu de base, le DLC et les profils spécialisés."
        ],
        tip: "Déplie « éléments empêchant le 100 % » pour voir précisément ce qui manque au profil sélectionné."
    },
    {
        id: "navigation",
        title: "Catégories, recherche et filtres",
        summary: "Réduire la liste aux objectifs utiles.",
        target: ".toolbar",
        points: [
            "La navigation latérale choisit les catégories visibles. La recherche accepte un nom, une région ou un terme présent dans une fiche.",
            "Les filtres séparent les états, contenus additionnels, modes de jeu, localisations, variantes et régions.",
            "Un objectif peut être automatique, manuel, mixte ou informatif. Le bandeau de portée signale les limites du filtre actif afin d’éviter une interprétation incorrecte."
        ],
        tip: "Commence par une catégorie, puis affine avec la recherche : la carte et la liste utilisent exactement le même périmètre."
    },
    {
        id: "map",
        title: "Carte d’Hyrule",
        summary: "Déplacement, zoom, marqueurs et ouverture des fiches.",
        target: ".mapPanel",
        points: [
            "Déplace la carte par glisser-déposer, utilise la molette ou les boutons pour zoomer, et le bouton maison pour revenir à la vue d’ensemble.",
            "Les marqueurs reprennent l’état des objectifs filtrés. Sélectionner un marqueur ouvre la même fiche que son entrée dans la liste.",
            "Certains objectifs se déroulent dans un intérieur ou ne possèdent pas de coordonnées fiables : ils restent accessibles dans la liste sans faux emplacement sur Hyrule."
        ],
        tip: "La carte et toutes ses tuiles sont intégrées à l’application et restent disponibles hors ligne."
    },
    {
        id: "guides",
        title: "Fiches, preuves et guides",
        summary: "Lire le statut, les solutions et leurs limites.",
        target: ".listPanel",
        points: [
            "Chaque fiche rassemble l’état détecté, la position disponible, les étapes utiles, les récompenses, coffres ou conditions associées.",
            "Une preuve automatique vient de la sauvegarde ; elle n’affirme jamais une action que les données du jeu ne permettent pas de distinguer.",
            "Les guides peuvent inclure des sources externes. Leur consultation nécessite Internet, mais le contenu essentiel de la fiche est déjà embarqué."
        ],
        tip: "Les mentions de limite ou de validation manuelle sont volontaires : elles évitent de transformer une absence de preuve en faux résultat."
    },
    {
        id: "manual",
        title: "Suivi manuel et sauvegarde des données",
        summary: "Cases personnelles, notes, import et export.",
        target: ".manualBar",
        points: [
            "Le suivi manuel complète l’analyse sans modifier le pourcentage officiel ni prétendre provenir de la sauvegarde du jeu.",
            "Tu peux revoir les validations, ajouter des notes et retirer une case depuis le panneau de contrôle.",
            "Les exports permettent de transférer ou sauvegarder tes validations et les données du Companion. Un import vérifie le format avant de remplacer les données locales."
        ],
        tip: "Effectue régulièrement « Sauvegarder toutes les données » si tu prévois de changer d’ordinateur."
    },
    {
        id: "routes",
        title: "Planificateur d’itinéraire",
        summary: "Créer, ordonner et conserver des sessions de jeu.",
        target: "#routePlanner",
        points: [
            "Ajoute les résultats filtrés ou un objectif précis à une session, puis choisis un point de départ facultatif.",
            "L’optimisation peut privilégier la distance directe, les régions ou les téléportations. Les étapes verrouillées conservent leur position.",
            "Le calcul est indicatif : il ne simule ni relief, météo, escalade, ennemis ni ressources consommées. Les sessions peuvent être dupliquées, importées ou exportées."
        ],
        tip: "Verrouille les étapes obligatoires avant d’optimiser pour conserver l’ordre des rendez-vous importants."
    },
    {
        id: "blood_moon",
        title: "Lune de sang",
        summary: "Interpréter le compteur interne et l’estimation.",
        target: "#bloodMoonPanel",
        points: [
            "Le panneau lit le compteur enregistré par BOTW et estime le temps de jeu actif restant avant le seuil normal des sept jours.",
            "Une lune peut être programmée puis reportée si les conditions du jeu ne permettent pas la cinématique à minuit.",
            "L’estimation dépend de la dernière sauvegarde lue : un jeu en pause, un menu ou une période non sauvegardée peut expliquer un écart avec le temps réel."
        ],
        tip: "Le pourcentage représente l’avancement du minuteur connu, pas une probabilité aléatoire de déclenchement."
    },
    {
        id: "dsu",
        title: "Gyroscope JoyConDSU",
        summary: "Manette, calibration, diagnostic et émulateur.",
        target: "#dsuControl",
        points: [
            "Sélectionne une manette compatible, puis active le moteur seulement lorsque ton émulateur doit recevoir ses mouvements.",
            "Le diagnostic mesure fréquence, retard, jitter, pertes et recalibrations. Une qualité insuffisante peut venir du Bluetooth, de la veille ou d’une autre application utilisant la manette.",
            "L’émulateur doit être configuré pour le serveur DSU local 127.0.0.1:26760. Le moteur reste désactivé par défaut et s’arrête proprement avec le Companion."
        ],
        tip: "Pose la manette immobile pendant la calibration et évite de lancer plusieurs serveurs DSU sur le même port."
    },
    {
        id: "application",
        title: "Mises à jour, aide et fermeture",
        summary: "Gérer l’application sans perdre tes données.",
        target: ".appActions",
        points: [
            "« Vérifier les mises à jour » consulte la dernière Release compatible avec un délai court. Le téléchargement démarre uniquement après confirmation, peut reprendre après une coupure et doit être vérifié avant toute installation.",
            "Le bouton Aide rouvre ce centre et permet de reprendre le parcours ou d’afficher directement un chapitre.",
            "Utilise « Quitter » pour arrêter proprement le serveur local et JoyConDSU. Les données personnelles restent dans le dossier de données de l’application, séparé de l’installation."
        ],
        tip: () => runtimePlatform.data_directory
            ? `Données et journaux locaux : ${runtimePlatform.data_directory}`
            : "Les données et journaux sont conservés dans le dossier de données de l’application, séparé du programme installé."
    }
];

const ESSENTIAL_TUTORIAL_STEPS = [
    {
        chapter: "privacy",
        title: "Bienvenue dans BOTW Companion",
        description: "Le Companion analyse ta progression sur cet ordinateur et reste utilisable sans connexion Internet.",
        detail: "Ta sauvegarde n’est pas envoyée. Seules les mises à jour et les sources externes utilisent Internet, lorsque tu les demandes.",
        target: "header"
    },
    {
        chapter: "save",
        title: "Vérifie la sauvegarde retenue",
        description: "L’émulateur, le slot, la date et l’aperçu confirment quelle partie est actuellement analysée.",
        detail: () => {
            const save = report?.sauvegarde || {};
            return `${save.emulateur || "Émulateur détecté"} • ${save.plateforme || runtimePlatform.label || "Système local"} • slot ${save.slot || "en cours de détection"}`;
        },
        target: "#savePreview"
    },
    {
        chapter: "sync",
        title: "Garde la progression à jour",
        description: "Choisis l’intervalle de lecture, mets la synchronisation en pause ou demande une lecture immédiate.",
        detail: "Une erreur temporaire ne remplace jamais le dernier rapport valide. L’historique récent explique chaque lecture.",
        target: ".syncSaveArea"
    },
    {
        chapter: "completion",
        title: "Deux mesures, deux usages",
        description: "L’anneau doré reproduit la carte officielle de BOTW ; l’anneau vert mesure les objectifs automatiquement vérifiables du profil choisi.",
        detail: "Leurs totaux sont différents. Déplie les éléments bloquants pour comprendre précisément ce qui manque au profil de complétion.",
        target: ".hero"
    },
    {
        chapter: "navigation",
        title: "Trouve ce qui t’intéresse",
        description: "Combine catégories, recherche et filtres pour définir les objectifs affichés dans la liste et sur la carte.",
        detail: "Les états automatique, manuel, mixte et informatif restent distincts afin de ne jamais confondre une preuve de sauvegarde avec une case personnelle.",
        target: ".toolbar"
    },
    {
        chapter: "map",
        title: "Explore la carte et les fiches",
        description: "Déplace et zoome la carte, puis sélectionne un marqueur ou un résultat pour ouvrir sa fiche détaillée.",
        detail: "Les objectifs intérieurs ou sans coordonnées fiables restent dans la liste plutôt que d’être placés arbitrairement sur Hyrule.",
        target: ".mapPanel"
    },
    {
        chapter: "manual",
        title: "Conserve tes validations personnelles",
        description: "Le suivi manuel, les notes et les exports complètent l’analyse automatique sans modifier le compteur officiel.",
        detail: "Le planificateur situé plus bas permet ensuite de regrouper ces objectifs en sessions et d’en optimiser l’ordre indicatif.",
        target: ".manualBar"
    },
    {
        chapter: "blood_moon",
        title: "Anticipe la lune de sang",
        description: "Ce panneau interprète le minuteur enregistré dans la dernière sauvegarde et les étapes de programmation du jeu.",
        detail: "L’estimation suit le temps de jeu actif connu. Une cinématique peut être reportée si les conditions ne sont pas réunies à minuit.",
        target: "#bloodMoonPanel"
    },
    {
        chapter: "dsu",
        title: "Active le gyroscope seulement si nécessaire",
        description: "JoyConDSU est inclus, mais reste désactivé tant que ton émulateur n’a pas besoin des mouvements de la manette.",
        detail: "Le bouton Aide permet de retrouver les 12 chapitres, dont la configuration DSU, les itinéraires, les sauvegardes et les mises à jour.",
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
        `<p class="eyebrow">BIEN DÉMARRER</p>` +
        `<h3>Choisis le niveau d’aide qui te convient</h3>` +
        `<p>Le parcours essentiel présente neuf repères directement dans l’interface. Les chapitres détaillés restent disponibles ici à tout moment.</p>` +
        `<div class="helpOverviewCards">` +
        `<article><b>Parcours guidé</b><span>9 étapes contextuelles • environ 3 minutes</span></article>` +
        `<article><b>Centre d’aide</b><span>12 chapitres complets • entièrement hors ligne</span></article>` +
        `</div>` +
        `<p class="helpPrivacyNote"><b>Aucune action n’est déclenchée pendant le parcours.</b> Les éléments sont seulement mis en évidence ; tes filtres, validations et sauvegardes ne sont jamais modifiés.</p>`;
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
        `<p class="eyebrow">CHAPITRE ${String(HELP_CHAPTERS.indexOf(chapter) + 1).padStart(2, "0")}</p>` +
        `<h3>${esc(chapter.title)}</h3>` +
        `<p>${esc(chapter.summary)}</p>` +
        `<ul>${chapter.points.map(point => `<li>${esc(point)}</li>`).join("")}</ul>` +
        `<p class="helpTip"><b>À retenir</b>${esc(tip)}</p>` +
        `<button class="showHelpTarget" type="button" data-start-chapter="${esc(chapter.id)}">Voir dans l’interface</button>`;
    if (focus) $("#helpContent").focus({ preventScroll: true });
}

function updateResumeTutorialButton() {
    const button = $("#resumeTutorial");
    if (!tutorialResume) {
        button.hidden = true;
        return;
    }
    button.hidden = false;
    button.textContent = `Reprendre à l’étape ${tutorialResume.index + 1}`;
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

function positionTutorial() {
    if (!tutorialState) return;
    const layer = $("#tutorialLayer"), card = $("#tutorialCard"),
        spotlight = $("#tutorialSpotlight"), target = visibleTutorialTarget(currentTutorialStep()),
        masks = [...layer.querySelectorAll(".tutorialMask")],
        viewportWidth = window.innerWidth, viewportHeight = window.innerHeight,
        margin = 12, gap = 16;

    if (!target) {
        setTutorialRectangle(masks[0], 0, 0, viewportWidth, viewportHeight);
        masks.slice(1).forEach(mask => setTutorialRectangle(mask, 0, 0, 0, 0));
        spotlight.hidden = true;
        card.classList.add("tutorialCard--centered");
        card.style.left = `${Math.max(margin, (viewportWidth - card.offsetWidth) / 2)}px`;
        card.style.top = `${Math.max(margin, (viewportHeight - card.offsetHeight) / 2)}px`;
        return;
    }

    const raw = target.getBoundingClientRect(), padding = 9,
        left = Math.min(viewportWidth - 7, Math.max(7, raw.left - padding)),
        top = Math.min(viewportHeight - 7, Math.max(7, raw.top - padding)),
        right = Math.max(7, Math.min(viewportWidth - 7, raw.right + padding)),
        bottom = Math.max(7, Math.min(viewportHeight - 7, raw.bottom + padding)),
        width = Math.max(0, right - left), height = Math.max(0, bottom - top);

    setTutorialRectangle(masks[0], 0, 0, viewportWidth, top);
    setTutorialRectangle(masks[1], right, top, viewportWidth - right, height);
    setTutorialRectangle(masks[2], 0, bottom, viewportWidth, viewportHeight - bottom);
    setTutorialRectangle(masks[3], 0, top, left, height);
    spotlight.hidden = false;
    setTutorialRectangle(spotlight, left, top, width, height);
    card.classList.remove("tutorialCard--centered");

    const cardWidth = card.offsetWidth, cardHeight = card.offsetHeight;
    let cardLeft = Math.min(
        Math.max(margin, left + width / 2 - cardWidth / 2),
        viewportWidth - cardWidth - margin
    );
    let cardTop;
    if (viewportHeight - bottom >= cardHeight + gap) {
        cardTop = bottom + gap;
    } else if (top >= cardHeight + gap) {
        cardTop = top - cardHeight - gap;
    } else if (viewportWidth - right >= cardWidth + gap) {
        cardLeft = right + gap;
        cardTop = Math.min(Math.max(margin, top + height / 2 - cardHeight / 2), viewportHeight - cardHeight - margin);
    } else if (left >= cardWidth + gap) {
        cardLeft = left - cardWidth - gap;
        cardTop = Math.min(Math.max(margin, top + height / 2 - cardHeight / 2), viewportHeight - cardHeight - margin);
    } else {
        cardTop = Math.max(margin, viewportHeight - cardHeight - margin);
    }
    card.style.left = `${cardLeft}px`;
    card.style.top = `${Math.min(cardTop, viewportHeight - cardHeight - margin)}px`;
}

function renderTutorialStep(focusHeading = false) {
    const step = currentTutorialStep(), total = tutorialState.steps.length,
        detail = typeof step.detail === "function" ? step.detail() : step.detail,
        last = tutorialState.index === total - 1,
        target = visibleTutorialTarget(step);
    $("#tutorialKind").textContent = tutorialState.kind === "essential"
        ? "PARCOURS ESSENTIEL"
        : "AIDE CONTEXTUELLE";
    $("#tutorialStepLabel").textContent = `Étape ${tutorialState.index + 1} sur ${total}`;
    $("#tutorialProgressBar").style.width = `${(tutorialState.index + 1) / total * 100}%`;
    $("#tutorialTitle").textContent = step.title;
    $("#tutorialDescription").textContent = step.description;
    $("#tutorialDetail").textContent = target
        ? detail
        : `${detail || ""} Cette partie de l’interface n’est pas disponible dans l’état actuel, mais l’explication reste accessible.`.trim();
    $("#previousTutorial").hidden = tutorialState.index === 0;
    $("#skipTutorial").hidden = tutorialState.kind !== "essential";
    $("#nextTutorial").textContent = last ? "Terminer" : "Suivant";
    if (target) {
        target.scrollIntoView({
            behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
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
        sync_interval: Number(localStorage.getItem(SYNC_INTERVAL_KEY)),
        map_content_mode: localStorage.getItem(MAP_MODE_KEY),
        completion_profile: localStorage.getItem(PROFILE_KEY),
        game_mode_filter: localStorage.getItem(MODE_FILTER_KEY)
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
        throw Error(data.erreur || "Migration des préférences impossible");
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
            label: "Sanctuaires terminés - coffres restants",
            count: remaining.length
        });
        treasures.types.sort(
            (left, right) =>
                left.label.localeCompare(
                    right.label,
                    "fr"
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
        mixed: "Automatique + manuel",
        automatic: "Automatique",
        manual: "Manuel",
        none: x.informational ? "Informatif" : "À faire"
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
                    "Enregistrement des itinéraires impossible"
                );
            }

            routesData.revision = data.revision;
            routesData.updated_at = data.updated_at;

            try {
                localStorage.removeItem(ROUTE_STORAGE_KEY)
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
    ].sort((a, b) => a.localeCompare(b, "fr"));

    select.innerHTML =
        '<option value="all">Toutes les variantes</option>' +
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
                        ? ' - indisponible'
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
            label: profile?.label || "Profil",
            note: p.mode || "Profil indisponible"
        };
    }

    const formula = report.referentiel_100.formula.expression,
        inventory = report.referentiel_100.inventory_constraints,
        inventoryNote = profile.id === "amiibo"
            ? ` Collection séparée : ${inventory.all_unique_armor} armures existent pour ${inventory.armor_inventory_limit} emplacements.`
            : "";
    return {
        available: true,
        label: profile.label,
        faits: p.faits || 0,
        total: p.total || 0,
        pourcentage: p.total
            ? 100 * p.faits / p.total
            : 0,
        note: `${profile.scope} Formule : ${formula}.${inventoryNote}`,
        blockers: p.blocking_categories || [], remaining: p.remaining || 0,
        effectiveProfile: p.effective_profile || profile.id, profileId: profile.id
    };
}

function renderCompletionBlockers(score) {
    const summary = $("#completionBlockerSummary"), list = $("#completionBlockerList"),
        details = $("#completionBlockers");
    if (!score.available) {
        summary.textContent = "Profil indisponible pour cette sauvegarde";
        list.innerHTML = ""; details.open = false; return;
    }
    if (!score.remaining) {
        summary.textContent = "Aucun élément n’empêche le 100 %";
        list.innerHTML = "<li>Ce profil est complet.</li>"; details.open = false; return;
    }
    summary.textContent = `${score.remaining.toLocaleString("fr-FR")} éléments empêchent le 100 %`;
    list.innerHTML = score.blockers.map(category => {
        const examples = category.examples.map(item => esc(item.name)).join(" • "),
            more = Math.max(0, category.remaining - category.examples.length);
        return `<li><b>${esc(category.label)} : ${category.remaining.toLocaleString("fr-FR")}</b>` +
            `<span>${examples}${more ? ` • +${more.toLocaleString("fr-FR")} autres` : ""}</span></li>`;
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
            "Estimation indisponible";

        $("#bloodMoonStatus").textContent =
            moon.status_label ||
            "Compteur interne absent.";

        $("#bloodMoonPhase").textContent =
            "Indisponible";

        $("#bloodMoonPercent").textContent = "-";
        $("#bloodMoonThreshold").textContent = "-";
        $("#bloodMoonScheduled").textContent = "-";
        $("#bloodMoonEvent").textContent = "-";

        $("#bloodMoonMeasuredAt").textContent =
            "Aucune mesure disponible";

        $("#bloodMoonInternal").textContent =
            "Aucune valeur exploitable dans la dernière sauvegarde.";

        $("#bloodMoonAccuracy").textContent =
            moon.accuracy_label || "-";

        $("#bloodMoonProgress").style.width = "0%";

        return;
    }

    const duration = bloodMoonDuration(
        moon.active_seconds_until_event
    ),
        savedAt =
            report?.synchronisation?.save_time;

    const phase =
        moon.scheduled
            ? "Cycle validé • programmée"
            : moon.status === "just_occurred"
                ? "Nouveau cycle"
                : "Cycle en cours • non programmée";

    $("#bloodMoonCountdown").textContent =
        `≈ ${duration} de jeu actif`;

    $("#bloodMoonPhase").textContent = phase;

    $("#bloodMoonPercent").textContent =
        `${Math.round(
            Number(moon.timer_progress_percent) || 0
        )} %`;

    $("#bloodMoonStatus").textContent =
        moon.scheduled
            ? "La lune de sang est validée : elle se déclenchera au prochain minuit autorisé."
            : "Temps restant estimé depuis la dernière sauvegarde avant le déclenchement réel.";

    $("#bloodMoonThreshold").textContent =
        moon.scheduled
            ? "Atteint"
            : `dans ≈ ${bloodMoonDuration(
                moon.active_seconds_until_threshold
            )}`;

    $("#bloodMoonScheduled").textContent =
        moon.scheduled
            ? "Validée"
            : `dans ≈ ${bloodMoonDuration(
                moon.active_seconds_until_scheduled
            )}`;

    $("#bloodMoonEvent").textContent =
        `dans ≈ ${duration}`;

    $("#bloodMoonMeasuredAt").textContent =
        savedAt
            ? `Mesure exacte de la sauvegarde à ${savedAt}`
            : "Mesure exacte de la dernière sauvegarde";

    $("#bloodMoonInternal").textContent =
        `Compteur ${
            Number(moon.timer_value).toLocaleString(
                "fr-FR",
                {
                    maximumFractionDigits: 1
                }
            )
        } / ${
            Number(moon.timer_target).toLocaleString("fr-FR")
        } • heure du jeu ${moon.game_time_label}`;

    $("#bloodMoonAccuracy").textContent =
        `Le compteur baisse uniquement pendant le jeu actif et se recale à chaque sauvegarde.${
            moon.may_be_delayed
                ? " Le déclenchement est actuellement susceptible d’être reporté."
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
        localStorage.getItem(DSU_SOURCE_KEY) ||
        "";

    select.replaceChildren();
    if (!controllers.length) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "Aucune manette détectée";
        select.appendChild(option);
        select.value = "";
        $("#dsuCapabilities").textContent =
            "Connecte une manette en USB ou Bluetooth puis attends la détection.";
        return null;
    }

    for (const controller of controllers) {
        const option = document.createElement("option");
        option.value = String(controller.id);
        const suffix = controller.compatible
            ? " - gyroscope disponible"
            : controller.kind === "joycon_single"
                ? " - associe les deux Joy-Con"
                : " - gyroscope indisponible";
        option.textContent = `${controller.name}${suffix}`;
        option.dataset.compatible = controller.compatible ? "1" : "0";
        select.appendChild(option);
    }

    const chosen = controllers.find(x => String(x.id) === String(preferred)) ||
        controllers.find(x => x.compatible) ||
        controllers[0];
    select.value = String(chosen.id);
    localStorage.setItem(DSU_SOURCE_KEY, String(chosen.id));

    const vidPid = controllerVidPid(chosen);
    const kind = chosen.kind === "joycon_pair"
        ? "Paire Joy-Con / grip"
        : chosen.type || "Manette";
    $("#dsuCapabilities").textContent = chosen.compatible
        ? `${kind}${vidPid} • gyroscope + accéléromètre disponibles`
        : chosen.kind === "joycon_single"
            ? `${kind}${vidPid} • utilise la paire Joy-Con combinée`
            : `${kind}${vidPid} • aucun gyroscope exploitable par SDL3`;
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
    return Number.isFinite(numeric) ? numeric.toLocaleString("fr-FR") : "-";
}

function renderDsuDiagnostic(state) {
    const diagnostic = state?.diagnostic || {
        status: "inactive",
        label: "Diagnostic inactif",
        summary: "Active le gyroscope pour mesurer la qualité du signal."
    };
    const telemetry = state?.telemetry || {};
    const quality = $("#dsuQuality");
    quality.textContent = diagnostic.label;
    quality.className = `quality-${diagnostic.status}`;
    $("#dsuQualitySummary").textContent = diagnostic.summary;
    $("#dsuReceivedRate").textContent = dsuMetric(telemetry.received_hz, 1, " Hz");
    $("#dsuSentRate").textContent = Number(telemetry.clients || 0) === 0 && telemetry.sent_hz !== undefined
        ? "En attente de l’émulateur"
        : dsuMetric(telemetry.sent_hz, 1, " Hz");
    $("#dsuSampleAge").textContent = dsuMetric(telemetry.sample_age_ms, 1, " ms");
    $("#dsuReceivedJitter").textContent = telemetry.received_jitter_mean_ms === undefined
        ? "-"
        : `${dsuMetric(telemetry.received_jitter_mean_ms, 2, " ms")} moy. • ${dsuMetric(telemetry.received_jitter_max_ms, 2, " ms")} max.`;
    $("#dsuSentJitter").textContent = telemetry.sent_jitter_mean_ms === undefined
        ? "-"
        : `${dsuMetric(telemetry.sent_jitter_mean_ms, 2, " ms")} moy. • ${dsuMetric(telemetry.sent_jitter_max_ms, 2, " ms")} max.`;
    $("#dsuTimestampErrors").textContent = telemetry.duplicate_timestamps === undefined
        ? "-"
        : `${dsuCounter(telemetry.duplicate_timestamps)} doublons • ${dsuCounter(telemetry.regressive_timestamps)} régressifs`;
    $("#dsuSentPackets").textContent = dsuCounter(telemetry.sent_packets);
    $("#dsuNetworkErrors").textContent = telemetry.send_errors === undefined
        ? "-"
        : `${dsuCounter(telemetry.send_errors)} UDP • ${dsuCounter(telemetry.invalid_requests)} requêtes invalides`;
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
        state_label: "État DSU inaccessible",
        message: "Le Companion ne peut pas interroger le serveur local.",
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
        state.log_path ? `Journal : ${state.log_path}` : null
    ].filter(Boolean).join("\n");
    $("#toggleDsu").textContent = state.running ? "Désactiver" : "Activer";
    $("#toggleDsu").classList.toggle("active", state.running);
    $("#dsuSource").disabled = dsuBusy || state.running;
    $("#toggleDsu").disabled =
        dsuBusy ||
        state.state === "unavailable" ||
        (!state.running && (!selectedSource || !selectedSource.compatible));
}

async function loadRuntimePlatform() {
    try {
        const response = await fetch("/api/version");
        const data = await response.json();
        if (!response.ok) {
            throw Error("Plateforme inaccessible");
        }
        runtimePlatform = {
            ...runtimePlatform,
            ...(data.platform || {})
        };
        $("#runtimePlatform").textContent =
            String(runtimePlatform.label || "Système local").toUpperCase();
        $("#dsuEngineLabel").textContent =
            runtimePlatform.native_dsu_engine || "DSU";
    } catch (_error) {
        $("#runtimePlatform").textContent = "SYSTÈME LOCAL";
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
        throw Error("Copie impossible dans ce navigateur");
    }
}

function scheduleDsu(state) {
    clearTimeout(dsuTimer);
    const active = state?.running || ["starting", "waiting_controller", "ready"].includes(state?.state);
const seconds = document.hidden ? 30 : active ? 2 : 3;
    dsuTimer = setTimeout(refreshDsu, seconds * 1000);
}

async function refreshDsu() {
    let state = null;
    try {
        const response = await fetch(`/api/dsu?t=${Date.now()}`);
        state = await response.json();
        if (!response.ok) {
            throw Error(state.message || "État DSU inaccessible");
        }
        renderDsu(state);
    } catch (error) {
        renderDsu({
            state: "error",
            state_label: "État DSU inaccessible",
            message: error.message,
            running: false
        });
    } finally {
        scheduleDsu(state);
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
            throw Error(state.message || "Commande DSU impossible");
        }
        toast(stop ? "Gyroscope désactivé" : "Serveur DSU activé - laisse la manette immobile");
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
    $("#refresh").disabled = true;

    try {
        const [
            reportResponse,
            manualResponse,
            routesResponse,
            preferencesResponse
        ] = await Promise.all([
            fetch("/api/report?" + Date.now()),
            fetch("/api/manual?" + Date.now()),
            fetch("/api/routes?" + Date.now()),
            fetch("/api/preferences?" + Date.now())
        ]);

        const data = await reportResponse.json(),
            manual = await manualResponse.json(),
            routes = await routesResponse.json(),
            preferences = await preferencesResponse.json();

        if (!preferencesResponse.ok) {
            throw Error(
                preferences.erreur ||
                "Préférences inaccessibles"
            );
        }

        preferencesData = preferences;
        if (
            preferencesData.values.tutorial_completed_version !== TUTORIAL_VERSION &&
            !onboardingShown
        ) {
            showOnboarding();
        }

        if (!reportResponse.ok) {
            throw Error(
                data.erreur ||
                "Analyse impossible"
            );
        }

        if (!manualResponse.ok) {
            throw Error(
                manual.erreur ||
                "Suivi manuel inaccessible"
            );
        }

        if (!routesResponse.ok) {
            throw Error(
                routes.erreur ||
                "Itinéraires inaccessibles"
            );
        }

        const catalogResponse = await fetch(
            "/api/catalog?revision=" +
            encodeURIComponent(
                data.report_revision_key
            )
        );

        const catalog = await catalogResponse.json();

        if (!catalogResponse.ok) {
            throw Error(
                catalog.erreur ||
                "Catalogue inaccessible"
            );
        }

        if (
            catalog.report_revision_key !==
            data.report_revision_key
        ) {
            throw Error(
                "La sauvegarde a changé pendant le chargement du catalogue; actualise la page"
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
        syncInterval = Number(
            preferenceValue("sync_interval", SYNC_INTERVAL_KEY, 30)
        );
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
                "Ancien itinéraire transféré dans les données de l’application"
            );
        }

        renderAll();

        if (showToast) {
            toast(
                "Sauvegarde, suivi et itinéraires relus"
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

    const saveDate = s.date
        ? s.date.replace(
            /^(\d{4})-(\d{2})-(\d{2}) (.*)$/,
            "$3/$2/$1 à $4"
        )
        : "-";

    $("#saveInfo").textContent =
        `Slot ${s.slot} • ${
            s.mode === "expert"
                ? "Mode Expert"
                : "Mode normal"
        } • ${saveDate} • ${s.chemin}`;

    renderSavePreview(s, saveDate);

    const emulatorLabel = String(s.emulateur || "Émulateur").toUpperCase();
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
        `${mapScore.faits.toLocaleString("fr-FR")} marqueurs sur ${mapScore.total.toLocaleString("fr-FR")}`;

    const formula =
        mapScore.selected_mode === "dlc"
            ? "Formule jeu + DLC"
            : "Formule jeu de base";

    $("#mapStatus").textContent =
        mapScore.visible_dans_le_jeu
            ? `Pourcentage officiel de la carte actuellement visible dans BOTW. ${formula}${
                mapScore.selection === "automatique"
                    ? " sélectionnée automatiquement."
                    : " imposée manuellement."
            }`
            : `Prévision exacte du pourcentage de carte. Ce compteur reste masqué dans BOTW jusqu’à la première victoire contre Ganon. ${formula}${
                mapScore.selection === "automatique"
                    ? " sélectionnée automatiquement."
                    : " imposée manuellement."
            }`;

    const labels = {
        korogus: "Korogus",
        sanctuaires_base: "Sanctuaires",
        marqueurs_carte:
            "Lieux + tours + créatures",
        sanctuaires_dlc:
            "Sanctuaires DLC",
        donjon_final_dlc:
            "Donjon final DLC"
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
            ? `${score.faits.toLocaleString("fr-FR")} éléments validés sur ${score.total.toLocaleString("fr-FR")}`
            : `${score.label} indisponible pour cette sauvegarde`;

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
        '<option value="all">Toutes les régions</option>' +
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
    const mode = save.mode === "expert" ? "Expert" : "normal",
        emulator = save.emulateur || "Émulateur",
        platform = save.plateforme || runtimePlatform.label || "Système local",
        revision = String(report.report_revision_key || `${save.slot}:${save.date}`),
        image = $("#saveCaption"),
        fallback = $("#saveCaptionFallback");

    $("#saveSlotTitle").textContent = `Slot ${save.slot} • Mode ${mode}`;
    $("#saveSlotDate").textContent = `Dernière sauvegarde : ${saveDate}`;
    $("#saveSlotSource").textContent = `${emulator} • ${platform}`;
    $("#savePreview").title = save.detection_mode || "Slot sélectionné automatiquement";
    fallback.textContent = `SLOT ${save.slot}`;

    if (saveCaptionRevision === revision) {
        return;
    }

    saveCaptionRevision = revision;
    image.hidden = true;
    fallback.hidden = false;
    image.alt = `Aperçu du slot ${save.slot}, mode ${mode}, sauvegardé le ${saveDate}`;
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
            "fr-FR",
            {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit"
            }
        )
        : "-"
}

function updateSync(meta, error = null) {
    meta = meta || {};

    const status =
        error
            ? "erreur"
            : meta.status || "initialisation";

    $("#syncStatus").textContent =
        error
            ? "Synchronisation temporairement indisponible"
            : meta.status_label ||
                "Première lecture en attente";

    $("#syncDot").className =
        `sync-${status}`;

    const mode =
        meta.save_mode === "expert"
            ? "Expert"
            : meta.save_mode === "normal"
                ? "normal"
                : "-";

    const candidate =
        meta.candidate_slot
            ? ` • candidat ${meta.candidate_slot}`
            : "";

    $("#syncTimes").textContent =
        error
            ? `${error} • dernier rapport conservé`
            : `Dernière lecture réussie à ${syncDate(meta.last_success_at)} • sauvegarde interne à ${meta.save_time || "-"} • slot ${meta.slot || "-"} (${mode})${candidate} • révision ${meta.report_revision || 0}`;

    const events = meta.events || [];

    $("#syncEvents").innerHTML =
        events.length
            ? events
                .map(
                    event =>
                        `<p><time>${esc(syncDate(event.at))}</time><span>${esc(event.message)}</span></p>`
                )
                .join("")
            : '<p>Aucun événement.</p>';
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
            "Arrêter BOTW Companion ? Le suivi manuel et les itinéraires déjà enregistrés seront conservés."
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
        `<main class="shutdownPage"><div class="panel"><h1>BOTW Companion est arrêté</h1><p>${esc(runtimePlatform.relaunch_hint)}</p></div></main>`;
}

async function checkSync(force = false) {
    $("#refresh").disabled = true;

    if (force) {
        updateSync({
            status: "analyse",
            status_label:
                "Lecture immédiate demandée",
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
                "Synchronisation impossible"
            );
        }

        if (data.changed) {
            await load(false);

            toast(
                "Nouvelle sauvegarde analysée et catalogue actualisé"
            );
        } else {
            updateSync(data.synchronisation);

            if (force) {
                toast(
                    "Sauvegarde relue - contenu inchangé"
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
                                        ? `${done.toLocaleString("fr-FR")}/${trackable.length.toLocaleString("fr-FR")}`
                                        : `${items.length.toLocaleString("fr-FR")} pts`,
                                hint =
                                    trackable.length
                                        ? `${done} terminé${done > 1 ? 's' : ''} sur ${trackable.length}`
                                        : `${items.length} point${items.length > 1 ? 's' : ''} informatif${items.length > 1 ? 's' : ''} - sans statut terminé`;

                            return `<label class="filterType ${selectedTypes.has(type.id) ? 'selected' : ''}" title="${esc(hint)}"><input type="checkbox" data-filter-type="${esc(type.id)}" ${selectedTypes.has(type.id) ? 'checked' : ''}><span>${esc(type.label)}</span><small class="filterProgress ${trackable.length ? '' : 'informational'}">${progress}</small></label>`
                        })
                        .join("");

                return `<details class="filterGroup" open><summary><span>${esc(group.label)}</span><small title="Filtres actifs">${checked}/${visibleTypes.length} filtres</small></summary><div>${types}</div></details>`;
            })
            .join("");

    $("#categories").innerHTML =
        `<div class="filterHeading"><b>Filtres de carte</b><span><button data-filter-action="all">Tout</button><button data-filter-action="none">Aucun</button></span></div>${groups}`;

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
            ? " • matériaux prêts"
            : "";

    return `${x.etoiles || "☆☆☆☆"}${
        x.possede
            ? ` • niveau ${x.niveau}/4`
            : " • non possédée"
    }${ready}`;
}

function renderItems() {
    refreshVariants();

    const items = filtered();

    $("#resultCount").textContent =
        `${items.length} résultat${items.length > 1 ? 's' : ''}`;

    $("#mapCount").textContent =
        `${items.filter(x => x.x != null && x.z != null).length} localisés`;

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
            : "Éléments filtrés";

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
                                ? `près de ${x.nearby}`
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
                        ].filter(Boolean).join(" • "))}</span>${x.raison ? `<span class="itemMeta">${esc(x.raison)}</span>` : ""}</span><span class="coords">${x.x != null ? `X ${x.x.toFixed(0)} · Z ${x.z.toFixed(0)}` : ""}</span></button>${x.x != null ? `<button type="button" class="routeAdd ${planned.has(itemId(x)) ? 'active' : ''}" data-route-add="${esc(itemId(x))}" aria-label="${planned.has(itemId(x)) ? 'Retirer' : 'Ajouter'} ${esc(x.name || x.display_name || x.id)} ${planned.has(itemId(x)) ? 'de' : 'à'} l’itinéraire" title="${planned.has(itemId(x)) ? 'Retirer de' : 'Ajouter à'} l’itinéraire">${planned.has(itemId(x)) ? '✓' : '+'}</button>` : ""}</div>`
                )
                .join("") +

                (
                    more
                        ? `<button id="showMoreResults" class="showMoreResults">Afficher ${Math.min(LIST_PAGE_SIZE, more)} résultats supplémentaires • ${more.toLocaleString("fr-FR")} restant${more > 1 ? 's' : ''}</button>`
                        : ""
                )
            : '<div class="empty">Aucun élément avec ces filtres.</div>';

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
            ? `Affichage volontaire de tous les modes : ${expert.toLocaleString("fr-FR")} placement${expert > 1 ? 's' : ''} exclusif${expert > 1 ? 's' : ''} au mode Expert est inclus.`
            : mode === "normal"
                ? "Les placements exclusifs au mode Expert sont masqués."
                : mode === "expert"
                    ? "Les placements communs et exclusifs au mode Expert sont affichables."
                    : "";

    $("#filterScopeNotice").innerHTML =
        `<b>Périmètre contrôlé</b><span>${esc(warning)} ${map.toLocaleString("fr-FR")} sur Hyrule • ${interior.toLocaleString("fr-FR")} sur cartes intérieures • ${list.toLocaleString("fr-FR")} seulement dans la liste.</span>${audit.status && audit.status !== "complete" ? '<strong>Les compteurs de référence nécessitent une vérification.</strong>' : ''}`;
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
        '<div class="detailLoading"><b id="detailTitle">Chargement de la fiche…</b><small>Les détails sont récupérés localement à la demande.</small></div>';

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
                    "Fiche inaccessible"
                );
            }

            if (
                payload.report_revision_key !==
                report.report_revision_key
            ) {
                throw Error(
                    "Cette fiche appartient à une autre révision de la sauvegarde"
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

            return `<button type="button" title="Zoomer sur ${group.length} éléments" aria-label="Zoomer sur ${group.length} éléments" data-cluster-x="${p.x}" data-cluster-y="${p.y}" class="marker cluster" style="left:${p.x / MAP_W * 100}%;top:${p.y / MAP_H * 100}%">${group.length}</button>`;
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

                return `<button type="button" title="${esc(point.label)}" aria-label="Étape ${index + 1} : ${esc(point.label)}" data-route-index="${index}" class="marker waypoint" style="left:${p.x / MAP_W * 100}%;top:${p.y / MAP_H * 100}%">${index + 1}</button>`
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

                return `<button type="button" title="Étape ${index + 1} - ${esc(point.name)}" aria-label="Étape planifiée ${index + 1} : ${esc(point.name)}" data-planner-index="${index}" class="marker plannerWaypoint ${point.locked ? 'locked' : ''}" style="left:${p.x / MAP_W * 100}%;top:${p.y / MAP_H * 100}%">${index + 1}</button>`
            }
        ).join("");

    const startMarker =
        start
            ? (() => {
                const p =
                    worldPoint(start);

                return `<button type="button" title="Départ - ${esc(start.label || 'point personnalisé')}" aria-label="Point de départ : ${esc(start.label || 'point personnalisé')}" class="marker routeStart" style="left:${p.x / MAP_W * 100}%;top:${p.y / MAP_H * 100}%">D</button>`
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
            ? `Le marqueur est placé aux coordonnées X ${x.x.toFixed(1)}, Z ${x.z.toFixed(1)}.`
            : "Cet objectif n’a pas encore de coordonnées fiables dans la base locale.";

    if (x.farm) {
        return `${coord} Ce point de farm reste toujours affiché : l’ennemi réapparaît après une lune de sang, même si une victoire antérieure est enregistrée. ${x.scalable ? "Sa famille et sa position sont fiables, mais sa variante peut avoir évolué avec la difficulté du monde." : "La variante statique indiquée provient des données de placement du jeu."}`;
    }

    const guide = {
        sanctuaires:
            `${coord} Active le point de téléportation, termine l’épreuve${x.trial ? ` « ${x.trial} »` : ""} et examine l’autel. Pense au coffre facultatif avant de sortir.${x.quest ? ` L’accès dépend de la quête « ${x.quest} ».` : ""}`,

        coffres_sanctuaires:
            `${coord} Retourne dans ce sanctuaire et vérifie chaque salle avant l’autel. ${x.raison || "Le coffre n’est pas validé dans la sauvegarde."}`,

        coffres_monde:
            `${coord} Le coffre possède un flag permanent : son ouverture sera détectée à la prochaine sauvegarde.${x.contenu ? ` Contenu identifié : ${x.contenu}.` : ""}`,

        coffres_donjons:
            `Explore le secteur ${x.secteur || "du donjon"} avant de le quitter. Ce coffre possède un flag permanent et sera validé automatiquement après sauvegarde.`,

        korogus:
            `${coord} Cherche le petit puzzle environnemental autour du point : pierres, cercle, fleurs, moulinet, ballon, souche ou offrande. Le type exact du puzzle n’est pas conservé dans la sauvegarde.`,

        tours:
            `${coord} Atteins le sommet puis examine le terminal Sheikah. La prochaine sauvegarde validera automatiquement la tour.`,

        lieux:
            `${coord} Traverse précisément cette zone à pied jusqu’à ce que son nom apparaisse à l’écran. Une simple proximité ou un survol peut ne pas déclencher le flag.`,

        quetes_sanctuaires:
            `${coord} Ce premier marqueur est le départ de la quête. La destination ${x.sanctuaire ? `« ${x.sanctuaire} »` : "du sanctuaire"} est listée séparément ci-dessous, avec les éventuels objectifs intermédiaires.`,

        quetes_principales:
            `${coord} Commence par le marqueur de départ puis consulte les objectifs détaillés ci-dessous. Le compagnon attend le flag officiel de fin, pas seulement l’activation de la quête.`,

        quetes_secondaires:
            `${coord} Le premier marqueur indique où commencer ou, pour le crossover Xenoblade, le premier indice. Le statut actuel est « ${x.statut} »${x.region ? ` dans la région ${x.region}` : ""}.`,

        souvenirs:
            `${coord} Rejoins précisément le marqueur puis déclenche la scène. Une simple visite du lieu ne suffit pas : la cinématique doit avoir été enregistrée.`,

        hinox:
            `${coord} Abats ce Hinox puis effectue une sauvegarde. Son flag individuel est celui utilisé pour la médaille de Kilton.`,

        talus:
            `${coord} Abats ce Lithorok puis effectue une sauvegarde. Attaque le gisement sur son corps pour infliger des dégâts.`,

        moldarquors:
            `${coord} Attire le Moldarquor avec une bombe posée au sol, fais-la exploser lorsqu’il bondit, puis attaque-le et sauvegarde.`,

        compendium:
            `Photographie ${x.name} avec le module appareil photo jusqu’à obtenir l’identification, ou achète l’image auprès du laboratoire antique d’Elimith lorsque cette option est disponible.`,

        armures:
            `Obtiens au moins une fois ${x.name}. La possession et son niveau réel (${x.etoiles || "☆☆☆☆"}) sont lus directement dans l’inventaire de la sauvegarde.`,

        armures_max:
            x.possede
                ? `Améliore ${x.name} chez une Grande Fée jusqu’au niveau 4. Niveau actuellement détecté : ${x.niveau}/4 (${x.etoiles}).`
                : `Obtiens d’abord ${x.name}, puis améliore-la quatre fois auprès des Grandes Fées.`,
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
        return `Zelda Wiki - article sur « ${itemName} »`;
    }

    const exact = {
        "BOTW Event Flow Viewer - flux de quête":
            "Visualiseur des flux d’événements BOTW",
        "BOTW Object Map":
            "Carte des objets BOTW (ObjMap)",
        "Zelda Dungeon Interactive Map":
            "Zelda Dungeon - carte interactive",
        "Zelda Dungeon - Leviathan Bones":
            "Zelda Dungeon - article sur les fossiles de baleine",
        "Zelda Dungeon - Sunken Treasure":
            "Zelda Dungeon - article sur les trésors engloutis",
        "Zelda Dungeon - Épreuves de l'Épée":
            "Zelda Dungeon - Épreuves de l’épée"
    };

    return exact[name] || name;
}

function guideSources(sources, itemName) {
    if (!sources?.length) {
        return "";
    }

    return `<div class="guideSources"><small>SOURCES DE CONTRÔLE</small>${sources.map(source => `<a href="${esc(source.url)}" target="_blank" rel="noreferrer">${esc(frenchSourceName(source.name, itemName))} ↗</a>`).join("")}</div>`;
}

function renderDetails(x) {
    const category =
        report.categories[x.categorie]?.label ||
        x.filter_label ||
        "Information cartographique";

    const displayLabels = {
        map_and_list:
            "Carte d'Hyrule et liste",
        interior_only:
            "Carte intérieure et liste",
        list_only:
            "Liste seulement"
    };

    const facts = [
        ["Région", x.region],
        ["Origine", x.content_origin_label],
        ["Placement", x.placement_label],
        ["Couverture", x.coverage_label],
        ["Affichage", displayLabels[x.display_scope]],
        ["Localisation", x.location_status_label],
        ["Mode", x.game_mode_label],
        ["Activité", x.activity_scope_label],
        ["Variante initiale", x.subtype],
        ["Récompense", x.reward],
        [
            "Farm lune de sang",
            x.farm
                ? "Toujours affiché"
                : null
        ],
        [
            "Évolution",
            x.scalable
                ? "Variante susceptible d’évoluer"
                : null
        ],
        ["Point proche", x.nearby],
        ["Épreuve", x.trial],
        ["Quête liée", x.quest],
        ["Sanctuaire", x.sanctuaire],
        ["Contenu", x.contenu],
        ["Secteur", x.secteur || x.section],
        ["Ensemble", x.set],
        [
            "Niveau",
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
            ? `<div class="detailSection"><h3>Matériaux pour atteindre ${"★".repeat(upgrade.niveau_cible)}</h3><div class="recipe">${upgrade.materiaux.map(m => `<div class="recipeRow ${m.disponible ? 'ready' : 'missing'}"><span>${esc(m.name)}</span><b>${m.possede} / ${m.requis}</b><small>${m.manque ? `manque ${m.manque}` : 'prêt'}</small></div>`).join("")}</div></div>`
            : "";

    const geo =
        x.geo_points || [];

    const geoBlock =
        geo.length
            ? `<div class="detailSection"><h3>${geo.length > 1 ? "Étapes et localisations" : "Localisation"}</h3><div class="geoPoints">${geo.map((p, i) => `<article class="geoPoint"><div><b>${esc(p.label)}</b><small>${esc(p.nearby ? `Près de ${p.nearby}${p.nearby_distance_m != null ? ` • environ ${p.nearby_distance_m} m` : ""}` : "Coordonnées du monde")}</small><span>X ${Number(p.x).toFixed(2)} • Z ${Number(p.z).toFixed(2)}</span></div><div class="geoActions"><button data-geo-center="${i}">Carte</button><button data-geo-copy="${i}">Copier</button><a href="https://objmap.zeldamods.org/#/map/z6,${p.x},${p.z}" target="_blank" rel="noreferrer">ObjMap ↗</a></div></article>`).join("")}</div></div>`
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
            ? `<div class="detailSection interiorCard"><h3>${esc(x.interior_map_label || "Carte intérieure")}</h3><p>${interiorPoints.length} coffre${interiorPoints.length > 1 ? 's' : ''} physique${interiorPoints.length > 1 ? 's' : ''} référencé${interiorPoints.length > 1 ? 's' : ''} dans les données du jeu.</p><div class="interiorPoints">${interiorPoints.map((p, i) => { const detail = guide?.chest_details?.[i] || p; return `<article><span>${detail.number || i + 1}</span><div><b>${esc(p.content || x.contenu || "Coffre")}</b>${detail.area ? `<small>${esc(detail.area)}</small>` : `<small>X ${Number(p.x).toFixed(2)} • Y ${Number(p.y).toFixed(2)} • Z ${Number(p.z).toFixed(2)}</small>`}${detail.access_label ? `<em>${esc(detail.access_label)}</em>` : ""}${detail.access ? `<p>${esc(detail.access)}</p>` : ""}</div></article>`; }).join("")}</div><small class="interiorNote">Ces coordonnées appartiennent à ${esc(x.interior_map)} : elles ne sont volontairement pas superposées à la carte d'Hyrule.</small></div>`
            : "";

    const stateLabels = {
        termine: "Terminé",
        actuel: "Étape actuelle",
        a_faire: "À faire",
        a_verifier: "À vérifier",
        verrouille: "Après activation"
    };

    const qualityBlock =
        guide?.quality_label
            ? `<div class="guideQuality quality${guide.quality_level}"><b>${esc(guide.quality_label)}</b><small>${esc(guide.verification_basis)}</small></div>`
            : "";

    const evidenceBlock =
        guide?.quest_evidence
            ? `<div class="guideEvidence"><small>PREUVE DU FLUX DE QUÊTE</small><p>${guide.quest_evidence.event_nodes} nœuds • ${guide.quest_evidence.event_actions} actions • ${guide.quest_evidence.message_references} références de dialogue</p></div>`
            : "";

    const trialBlock =
        guide?.trial_rooms?.length
            ? `<div class="trialRooms"><h3>Salles de ce niveau</h3>${guide.trial_rooms.map(room => `<article class="trialRoom ${esc(room.kind)}"><span>${room.floor}</span><div><small>${esc(room.kind_label)}</small><b>${esc(room.enemies)}</b><p>${esc(room.strategy)}</p></div></article>`).join("")}</div>`
            : "";

    const bossBlock =
        guide?.boss_profile
            ? `<div class="guideBoss"><small>PROFIL DU COMBAT</small><b>${esc(guide.boss_profile.variant)}</b><p><strong>Point faible :</strong> ${esc(guide.boss_profile.weak_point)}</p>${guide.boss_profile.scaling ? `<p>${esc(guide.boss_profile.scaling)}</p>` : ""}</div>`
            : "";

    const guideBlock =
        guide
            ? `<div class="detailSection guideCard"><div class="guideTitle"><h3>Fiche d’accompagnement personnalisée</h3>${guide.specificity_label ? `<span>${esc(guide.specificity_label)}</span>` : ""}</div>${qualityBlock}<p class="guideSummary">${esc(guide.summary)}</p>${guide.mechanic ? `<div class="guideMechanic"><small>MÉCANIQUE</small><b>${esc(guide.mechanic)}</b></div>` : ""}${bossBlock}<div class="currentAction"><small>PROCHAINE ACTION</small><b>${esc(guide.current_action)}</b></div>${guideList("Prérequis", guide.prerequisites)}${guideList("Préparation", guide.preparation)}${evidenceBlock}${trialBlock}${guide?.trial_rooms?.length ? "" : guideList("Solution détaillée", guide.detailed_steps, true, "solution")}${guide.chest_solution ? `<div class="guideChest"><small>COFFRE DU SANCTUAIRE</small><p>${esc(guide.chest_solution)}</p></div>` : ""}${guideList("Récompenses", guide.rewards, false, "rewards")}<div class="guideSteps">${(guide.steps || []).map((s, i) => `<article class="guideStep ${esc(s.state)}"><span>${i + 1}</span><div><b>${esc(s.title)}</b><p>${esc(s.instruction)}</p><small>${esc(stateLabels[s.state] || s.state)}</small></div>${s.geo_point_index != null && geo[s.geo_point_index] ? `<button data-guide-center="${s.geo_point_index}">Carte</button>` : ""}</article>`).join("")}</div>${guideList("Conseils", guide.tips, false, "tips")}${guideList("À savoir", guide.warnings, false, "warnings")}<div class="completionProof"><small>${guide.completion.automatic === false ? "SUIVI" : "VALIDATION AUTOMATIQUE"}</small><p>${esc(guide.completion.condition)}</p></div>${guideSources(guide.sources, x.name || "cet objectif")}</div>`
            : `<div class="detailSection"><h3>Comment le terminer</h3><p>${esc(helpFor(x))}</p></div>`;

    const manual =
        manualEntry(x),
        farmWarning =
            x.farm
                ? "Cet état n’enlève jamais ce point de farm de sa catégorie : l’ennemi réapparaît à la lune de sang."
                : "La validation reste conservée après une nouvelle analyse de la sauvegarde.";

    const scopeBlock =
        x.coverage_note
            ? `<div class="detailSection scopeWarning"><h3>Limite de couverture</h3><p>${esc(x.coverage_note)}</p></div>`
            : "";

    const manualBlock =
        `<div class="detailSection manualTracking"><h3>Suivi manuel persistant</h3><div class="statusSplit"><span><small>Sauvegarde</small><b>${x.termine ? 'Validé automatiquement' : 'Non validé automatiquement'}</b></span><span><small>Personnel</small><b>${manual.completed ? 'Validé manuellement' : 'Non coché'}</b></span></div><label class="manualCheck"><input id="manualComplete" type="checkbox" ${manual.completed ? 'checked' : ''}><span>Marquer cet objectif comme fait manuellement</span></label><label class="manualNoteLabel">Note personnelle<textarea id="manualNoteInput" maxlength="1000" placeholder="Optionnel : record, coffre vérifié, prochaine action…">${esc(manual.note || "")}</textarea></label><button id="saveManualNote">Enregistrer la note</button><p class="manualHint">${esc(farmWarning)}</p></div>`;

    const inRoute =
        routeIds().has(itemId(x));

    $("#detailContent").innerHTML =
        `<p class="detailEyebrow">${esc(category)}</p><h2 id="detailTitle">${esc(x.name || x.id)}</h2><p class="detailMeta">${esc([x.region, x.dlc ? "DLC" : null].filter(Boolean).join(" • "))}</p><span class="detailStatus"><i class="dot ${stateClass(x)}" aria-hidden="true"></i>${esc(trackingLabel(x))}</span>${facts.length ? `<div class="detailFacts">${facts.map(([k, v]) => `<div class="detailFact"><small>${esc(k)}</small>${esc(v)}</div>`).join("")}</div>` : ""}${scopeBlock}${manualBlock}${guideBlock}${geoBlock}${interiorBlock}${recipe}${coords && !geo.length ? `<div class="detailSection"><h3>Coordonnées BOTW</h3><p>X ${x.x.toFixed(2)} • Z ${x.z.toFixed(2)}</p></div>` : ""}<div class="detailActions">${coords ? `<button id="detailRoute">${inRoute ? 'Retirer de' : 'Ajouter à'} l’itinéraire</button><button id="detailCenter">Centrer sur la carte</button><button id="copyCoords">Copier le point principal</button><a href="${objmap}" target="_blank" rel="noreferrer">ObjMap ↗</a>` : ""}<a href="${search}" target="_blank" rel="noreferrer">Chercher un guide ↗</a></div>`;

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
                    "Coordonnées copiées"
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
                            "Coordonnées copiées"
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
        `${completed.toLocaleString("fr-FR")} objectif${completed === 1 ? '' : 's'} coché${completed === 1 ? '' : 's'}`;

    $("#manualNote").textContent =
        `${notes} note${notes === 1 ? '' : 's'} • révision ${manualTracking.revision} • séparé du score automatique`;

    $("#toggleManualReview").textContent =
        `Validations (${completed.toLocaleString("fr-FR")})`;

    renderManualReview();
}

function manualSearchText(value) {
    return String(value || "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLocaleLowerCase("fr");
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

            return byDate || left.name.localeCompare(right.name, "fr");
        });
}

function manualDate(value) {
    if (!value) {
        return "date inconnue";
    }

    const date = new Date(value);

    return Number.isNaN(date.getTime())
        ? "date inconnue"
        : date.toLocaleString("fr-FR", {
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
        ).entries()].sort((left, right) => left[1].localeCompare(right[1], "fr"));

    categorySelect.innerHTML =
        '<option value="all">Toutes les catégories</option>' +
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
        ? `${records.length.toLocaleString("fr-FR")} validation${records.length === 1 ? '' : 's'} manuelle${records.length === 1 ? '' : 's'} • ${filtered.length.toLocaleString("fr-FR")} affichée${filtered.length === 1 ? '' : 's'}`
        : "Aucun objectif coché manuellement.";

    if (!filtered.length) {
        list.innerHTML = `<div class="manualReviewEmpty">${records.length ? "Aucune validation ne correspond à cette recherche." : "Les objectifs cochés manuellement apparaîtront ici."}</div>`;
        return;
    }

    list.innerHTML = filtered.map(record => {
        const status = record.item
            ? record.automatic
                ? "Aussi validé automatiquement"
                : "Non validé automatiquement"
            : "Fiche absente du catalogue actuel",
            meta = [
                record.region,
                status,
                manualDate(record.entry.updated_at)
            ].filter(Boolean).join(" • "),
            note = record.entry.note
                ? `<p class="manualReviewNote">Note : ${esc(record.entry.note)}</p>`
                : "";

        return `<article class="manualReviewItem"><div><span class="manualReviewCategory">${esc(record.categoryLabel)}</span><h3>${esc(record.name)}</h3><p>${esc(meta)}</p>${note}</div><div class="manualReviewItemActions"><button type="button" data-manual-open="${esc(record.trackingId)}"${record.item ? "" : " disabled"}>Ouvrir la fiche</button><label class="manualReviewToggle"><input type="checkbox" checked data-manual-uncheck="${esc(record.trackingId)}"> Validé</label></div></article>`;
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
        `Annuler la validation manuelle de « ${record.name} » ? La note personnelle sera conservée.`
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
                "Enregistrement impossible"
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
                ? "Validation manuelle enregistrée"
                : "Validation manuelle annulée"
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
                    "Restauration impossible"
                );
            }
            await load(false);
            toast(
                "Suivi, itinéraires et préférences restaurés"
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
                "Import impossible"
            );
        }

        manualTracking = data;

        renderAll();

        toast(
            "Suivi manuel importé et fusionné"
        );

    } catch (error) {
        toast(
            error.message ||
            "Fichier invalide",
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
                "Cet élément n’a pas de coordonnées fiables",
                true
            );

            return;
        }

        if (
            routeState.entries.length >=
            ROUTE_LIMIT
        ) {
            toast(
                `Une session est limitée à ${ROUTE_LIMIT} étapes`,
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
            "Aucun nouveau résultat localisé à ajouter",
            true
        );
    } else {
        toast(
            `${added.length} étape${added.length > 1 ? 's' : ''} ajoutée${added.length > 1 ? 's' : ''}${available.length > capacity ? ` • limite de ${ROUTE_LIMIT} atteinte` : ''}`
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
            "Ajoute au moins deux étapes",
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
        "Ordre optimisé - étapes verrouillées et indisponibles conservées"
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
                    "Point personnalisé"
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
            ? `${points.length} étape${points.length > 1 ? 's' : ''} • ${formatDistance(total)}${missing ? ` • ${missing} indisponible${missing > 1 ? 's' : ''}` : ''}`
            : "Aucune étape sélectionnée.";

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
        `Départ : ${
            routeState.start
                ? `${routeState.start.label} - X ${Math.round(routeState.start.x)}, Z ${Math.round(routeState.start.z)}`
                : "premier objectif"
        }`;

    $("#routeRegions").textContent =
        `Régions : ${
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
                                "Région inconnue";

                        return `<article class="routeStep ${value.item ? '' : 'unavailable'}" data-route-step="${stateIndex}"><span>${index + 1}</span><div><b>${esc(name)}</b><small>${value.item ? `${esc(region)} • ${leg.index === 1 && !routeState.start ? "départ" : `+ ${formatDistance(leg.distance)}`} • cumul ${formatDistance(leg.cumulative)}` : `Étape indisponible dans le catalogue actuel • conservée avec ses anciennes informations`}</small></div><div class="routeStepActions">${value.item ? `<button data-route-focus="${esc(entry.tracking_id)}" title="Voir sur la carte" aria-label="Voir ${esc(name)} sur la carte">⌖</button>` : ""}<button data-route-up="${stateIndex}" title="Monter" aria-label="Monter ${esc(name)}">↑</button><button data-route-down="${stateIndex}" title="Descendre" aria-label="Descendre ${esc(name)}">↓</button><button data-route-lock="${stateIndex}" class="${entry.locked ? 'active' : ''}" title="Verrouiller cette position" aria-label="${entry.locked ? 'Déverrouiller' : 'Verrouiller'} la position de ${esc(name)}">${entry.locked ? '🔒' : '○'}</button><button data-route-remove="${esc(entry.tracking_id)}" title="Retirer" aria-label="Retirer ${esc(name)} de l’itinéraire">×</button></div></article>`
                    }
                )
                .join("")
            : '<div class="empty">Ajoute des objectifs depuis les résultats ou une fiche.</div>';

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
            "L’itinéraire est vide",
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

                `Départ : ${
                    payload.start
                        ? `${payload.start.label} (X ${Math.round(payload.start.x)}, Z ${Math.round(payload.start.z)})`
                        : "premier objectif"
                }`,

                `Distance géographique : ${formatDistance(payload.total_distance_m)}`,

                `Régions : ${payload.regions.join(", ")}`,

                "",

                ...payload.steps.map(
                    step =>
                        step.available
                            ? `${step.order}. ${step.name} - ${step.region || "région non indiquée"} - X ${Number(step.x).toFixed(0)}, Z ${Number(step.z).toFixed(0)} - +${formatDistance(step.distance_from_previous_m)}${step.locked ? " - verrouillée" : ""}`
                            : `${step.order}. ${step.name} - indisponible dans le catalogue actuel, conservée${step.locked ? " - verrouillée" : ""}`
                ),

                "",

                "Distance indicative : la stratégie organise les objectifs mais ne simule ni relief, météo, escalade ni dangers."

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
    name = "Nouvelle session"
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
            "Le planificateur est limité à 100 sessions",
            true
        );

        return;
    }

    const session =
        routeSessionTemplate(
            copy
                ? `${routeState.name} - copie`
                : "Nouvelle session"
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
            ? "Session dupliquée"
            : "Nouvelle session créée"
    );
}

function deleteRouteSession() {
    if (
        Object.keys(
            routesData.sessions
        ).length === 1
    ) {
        toast(
            "Crée une autre session avant de supprimer celle-ci",
            true
        );

        return;
    }

    if (
        !confirm(
            `Supprimer définitivement la session « ${routeState.name} » ?`
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
                "Import impossible"
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
            "Session importée sans supprimer les itinéraires existants"
        );

    } catch (error) {
        toast(
            error.message ||
            "Fichier d’itinéraire invalide",
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
                "Point choisi sur la carte"
        });

        routePickStart = false;

        mapEl.classList.remove(
            "pickStart"
        );

        $("#pickRouteStart").classList.remove(
            "active"
        );

        toast(
            "Point de départ défini"
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
        localStorage.setItem(
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
        localStorage.setItem(
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
        localStorage.setItem(
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

        localStorage.setItem(
            SYNC_INTERVAL_KEY,
            String(syncInterval)
        );
        savePreference("sync_interval", syncInterval);

        scheduleSync();

        toast(
            `Vérification toutes les ${syncInterval} secondes`
        );
    };

$("#pauseSync").onclick =
    () => {
        syncPaused =
            !syncPaused;

        $("#pauseSync").textContent =
            syncPaused
                ? "Reprendre"
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
                "Synchronisation automatique en pause"
            )
        }
    };

$("#quitCompanion").onclick =
    quitCompanion;

$("#dsuSource").onchange =
    () => {
        localStorage.setItem(DSU_SOURCE_KEY, $("#dsuSource").value);
        refreshDsu();
    };

$("#toggleDsu").onclick =
    toggleDsu;

$("#openHelp").onclick =
    () => showHelp(null, $("#openHelp"));

$("#checkUpdates").onclick =
    () => checkForUpdates(true);

$("#downloadUpdate").onclick =
    startUpdateDownload;

$("#cancelUpdateDownload").onclick =
    async () => {
        try {
            await updateDownloadAction("cancel");
        } catch (_error) {
            toast("Impossible d’annuler le téléchargement", true);
        }
    };

$("#retryUpdateDownload").onclick =
    async () => {
        try {
            await updateDownloadAction("retry");
        } catch (_error) {
            toast("Impossible de reprendre le téléchargement", true);
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
        tutorialState.index = Math.max(0, tutorialState.index - 1);
        renderTutorialStep();
    };

$("#nextTutorial").onclick =
    () => {
        if (!tutorialState) return;
        if (tutorialState.index < tutorialState.steps.length - 1) {
            tutorialState.index += 1;
            renderTutorialStep();
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
                ? "Clique sur la carte pour placer le départ"
                : "Sélection du départ annulée"
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
                "Ouvre d’abord une fiche localisée",
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
            "Départ défini depuis la fiche ouverte"
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
                "Saisis des coordonnées X et Z valides",
                true
            );

            return;
        }

        setRouteStart({
            x,
            z,
            label:
                "Coordonnées personnalisées"
        });

        toast(
            "Coordonnées de départ appliquées"
        );
    };

$("#clearRouteStart").onclick =
    () => {
        setRouteStart(null);

        toast(
            "Le premier objectif redevient le départ"
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
                "Le nom de session ne peut pas être vide",
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
            "Stratégie enregistrée pour cette session"
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
                "Vider toutes les étapes de cette session ?"
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
                ? "Masquer"
                : "Afficher";

        $("#toggleRoute").setAttribute(
            "aria-expanded",
            String(hidden)
        );
    };

sendHeartbeat();
