/* Persist the presentation language without changing personal data. */
(() => {
    const key = 'botw-companion-language';
    const valid = value => value === 'fr' || value === 'en';
    const current = document.documentElement.lang === 'en' ? 'en' : 'fr';
    const url = new URL(window.location.href);
    const explicit = url.searchParams.get('lang');
    const cookie = document.cookie.match(/(?:^|;\s*)botw-language=(fr|en)(?:;|$)/)?.[1];
    let saved;
    try { saved = localStorage.getItem(key); } catch (_) { /* Storage may be disabled. */ }
    const desired = valid(explicit) ? explicit : valid(cookie) ? cookie : valid(saved) ? saved : current;
    function remember(language) {
        try { localStorage.setItem(key, language); } catch (_) { /* The cookie remains usable. */ }
        document.cookie = `botw-language=${language}; Path=/; Max-Age=63072000; SameSite=Strict`;
    }
    remember(desired);
    if (desired !== current) {
        document.documentElement.dataset.languageNavigation = "true";
        url.searchParams.set('lang', desired);
        window.location.replace(url.href);
        return;
    }
    document.addEventListener('DOMContentLoaded', () => {
        const select = document.getElementById('languageSelect');
        if (!select) return;
        select.value = current;
        select.addEventListener('change', () => {
            if (!valid(select.value) || select.value === current) return;
            remember(select.value);
            document.documentElement.dataset.languageNavigation = "true";
            window.dispatchEvent(new Event('botw:language-navigation'));
            const next = new URL(window.location.href);
            next.searchParams.set('lang', select.value);
            // Carry the non-secret tab identity into the new history entry.
            // The current document has already stripped its launch token.
            const client = window.BOTWBrowserSession?.clientId;
            if (client) {
                const fragment = new URLSearchParams(next.hash.slice(1));
                fragment.set('browser-client', client);
                next.hash = fragment.toString();
            }
            window.location.assign(next.href);
        });
    });
})();
