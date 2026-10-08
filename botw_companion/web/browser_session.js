/* Reuse one tab across an assisted update; never automate unrelated tabs. */
(() => {
    const fragment = new URLSearchParams(location.hash.slice(1));
    const clientId = fragment.get('browser-client') || history.state?.botwBrowserClient || crypto.randomUUID();
    // Keep identity in this history entry, not in storage shared or copied
    // between tabs. The application may safely remove its launch fragment.
    history.replaceState({...history.state, botwBrowserClient: clientId}, '', location.href);
    const native = window.fetch.bind(window);
    let token, stop, timer, pending = null, stopped = false, leaving = false;
    let channel;
    try { channel = new BroadcastChannel('botw-companion-update'); } catch (_) { /* Polling remains usable. */ }
    const en = () => document.documentElement.lang === 'en';
    function retire() {
        if (stopped || leaving) return;
        stopped = true;
        clearTimeout(timer);
        stop();
        try { window.close(); } catch (_) { /* Closing may be restricted by the browser. */ }
        // Manually opened tabs may not be script-closable. Make them inert,
        // without navigating them to an unavailable port or opening more tabs.
        const main = document.createElement('main');
        main.className = 'shutdownPage';
        const panel = document.createElement('div');
        panel.className = 'panel';
        const title = document.createElement('h1');
        title.textContent = en() ? 'This BOTW Companion tab is inactive' : 'Cet onglet BOTW Companion n’est plus actif';
        const text = document.createElement('p');
        text.textContent = en() ? 'The updated application uses another tab. You can close this tab.'
            : 'L’application à jour utilise un autre onglet. Tu peux fermer cet onglet.';
        panel.append(title, text); main.append(panel);
        document.body.replaceChildren(main);
    }
    function begin(handoff) {
        if (stopped || !handoff?.id) return;
        pending = handoff;
        stop();
        clearTimeout(timer);
        if (handoff.client_id !== clientId) { retire(); return; }
        poll();
    }
    async function version() {
        const controller = new AbortController();
        const deadline = setTimeout(() => controller.abort(), 2000);
        try {
            const response = await native('/api/version', {cache: 'no-store', signal: controller.signal});
            if (!response.ok) return null;
            const identity = await response.json();
            return identity.application === 'BOTW Companion' ? identity : null;
        } finally { clearTimeout(deadline); }
    }
    async function claim(identity, handoff) {
        const controller = new AbortController();
        const deadline = setTimeout(() => controller.abort(), 2000);
        try {
            const response = await native('/api/browser/claim', {
                method: 'POST', signal: controller.signal,
                headers: {'Content-Type': 'application/json', 'X-BOTW-Session-Token': identity.session_token},
                body: JSON.stringify({id: handoff.id, client_id: clientId})
            });
            return response.ok ? (await response.json()).browser_handoff : null;
        } finally { clearTimeout(deadline); }
    }
    async function poll() {
        if (stopped || leaving) return;
        clearTimeout(timer);
        try {
            const identity = await version();
            if (stopped || leaving) return;
            const handoff = identity?.browser_handoff;
            // An ordinary restart may have no update handoff at all. A
            // document from that previous server must not keep stale assets.
            if (identity && identity.session_token !== token && !handoff) { retire(); return; }
            if (pending && identity && identity.session_token !== token &&
                (!handoff || handoff.id !== pending.id)) { retire(); return; }
            // Existing claims only retire documents from the previous server.
            // A fresh page already served by the current server must stay open.
            const previousDocument = pending || (identity && identity.session_token !== token);
            const canAcknowledge = handoff && !handoff.claimed_by &&
                (!handoff.client_id || handoff.client_id === clientId);
            if (handoff && (!pending || pending.id === handoff.id) &&
                (previousDocument || canAcknowledge)) {
                const state = await claim(identity, handoff);
                if (stopped || leaving) return;
                if (state?.claimed_by && state.claimed_by !== clientId && previousDocument) { retire(); return; }
                if (state?.claimed_by === clientId && identity.session_token !== token) {
                    const url = new URL(location.href);
                    url.hash = new URLSearchParams({'session': identity.session_token, 'browser-client': clientId}).toString();
                    channel?.postMessage({type: 'claimed', client_id: clientId});
                    // A fragment-only replacement would keep the old document.
                    // Keep the same tab/history entry, but load the new assets.
                    history.replaceState({...history.state, botwBrowserClient: clientId}, '', url.href);
                    location.reload();
                    return;
                }
                if (state?.claimed_by === clientId && !pending) return;
            }
        } catch (_) { /* Installation may take several minutes, including consent and rollback. */ }
        if (!stopped && !leaving) timer = setTimeout(poll, pending ? 500 : 30000);
    }
    window.BOTWBrowserSession = {
        clientId,
        init(sessionToken, onStop) {
            token = sessionToken; stop = onStop;
            listen();
            poll();
        },
        installed(handoff) {
            channel?.postMessage({type: 'handoff', handoff, session_token: token});
            begin(handoff);
        }
    };
    function listen() {
        if (channel) channel.onmessage = event => {
            if (event.data?.type === 'handoff' && event.data.session_token === token) begin(event.data.handoff);
            // Recheck the server instead of closing a current page on a delayed
            // announcement from a previous update.
            if (event.data?.type === 'claimed' && event.data.client_id !== clientId) poll();
        };
    }
    window.addEventListener('pagehide', () => { leaving = true; clearTimeout(timer); channel?.close(); });
    window.addEventListener('pageshow', event => {
        if (!event.persisted || stopped) return;
        leaving = false;
        try { channel = new BroadcastChannel('botw-companion-update'); listen(); } catch (_) { /* Optional. */ }
        poll();
    });
})();
