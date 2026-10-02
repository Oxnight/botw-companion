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
            const next = new URL(window.location.href);
            next.searchParams.set('lang', select.value);
            window.location.assign(next.href);
        });
    });
})();
