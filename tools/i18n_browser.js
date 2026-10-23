import {FluentBundle, FluentResource, FluentNumber} from '@fluent/bundle';

function immutable(value) {
    if (value && typeof value === 'object') {
        Object.values(value).forEach(immutable);
        Object.freeze(value);
    }
    return value;
}
function initialize(input) {
    const data = immutable(input);
    class SharedNumber extends FluentNumber {
        toString(scope) {
            // Babel emits Latin digits without incidental bidi marks. Match that
            // numeric contract; never strip characters from supplied string values.
            return super.toString(scope).replace(/[\u061c\u200e\u200f]/g, '');
        }
    }
    const number = (value, options = {}) => new SharedNumber(value, {...options, numberingSystem: 'latn'});
    const bundle = new FluentBundle(data.locale.format_locale, {useIsolating: false, functions: {
        NUMBER([value], options) {
            if (!(value instanceof FluentNumber)) throw new TypeError('NUMBER requires a number');
            return number(value.valueOf(), {...value.opts,
                ...Object.fromEntries(Object.entries(options).map(([key, child]) => [key, child.valueOf()]))});
        }
    }});
    const errors = bundle.addResource(new FluentResource(data.messages));
    if (errors.length || !data.registry.locales[data.locale.id]
        || Object.keys(data.contract).some(identity => !bundle.hasMessage(identity))) {
        throw new Error('Invalid localization resources');
    }
    const resolve = value => typeof value === 'string' ? data.registry.aliases[value.toLowerCase()] : undefined;
    function t(identity, values = {}) {
        const contract = data.contract[identity];
        if (!contract || Object.keys(values).sort().join('\0') !== [...contract.params].sort().join('\0')) {
            throw new Error(`Invalid message or parameters: ${identity}`);
        }
        if (Object.values(values).some(value => !['string', 'number'].includes(typeof value)
            || (typeof value === 'number' && !Number.isFinite(value)))) {
            throw new Error(`Invalid parameter type: ${identity}`);
        }
        const errors = [];
        const message = bundle.getMessage(identity);
        if (!message?.value) throw new Error(`Missing message: ${identity}`);
        const parameters = Object.fromEntries(Object.entries(values).map(([key, value]) =>
            [key, typeof value === 'number' ? number(value) : value]));
        const result = bundle.formatPattern(message.value, parameters, errors);
        if (errors.length) throw new Error(`Cannot format message: ${identity}`);
        return result;
    }
    return Object.freeze({t, resolve, registry: data.registry, failed: false,
        locale: data.locale.id, direction: data.locale.direction, formatLocale: data.locale.format_locale});
}
// Initialize before application startup so early errors use this catalog.
try {
    globalThis.BOTWI18n = initialize(globalThis.BOTWLocaleData);
} catch (_) {
    // Generated HTML carries a localized emergency explanation independently
    // of the missing/damaged script catalog. No retry or data write is needed.
    const explanation = () => document.querySelector('meta[name="botw-localization-error"]')?.content
        || 'BOTW Companion: localization resources are unavailable.';
    globalThis.BOTWI18n = Object.freeze({failed: true, t() { throw new Error(explanation()); }});
    document.addEventListener('DOMContentLoaded', () => {
        const main = document.createElement('main');
        main.className = 'shutdownPage';
        const panel = document.createElement('div');
        panel.className = 'panel';
        const text = document.createElement('p');
        text.textContent = explanation();
        panel.append(text); main.append(panel);
        document.body.replaceChildren(main);
    }, {once: true});
}
