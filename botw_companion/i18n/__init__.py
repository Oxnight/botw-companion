from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
import json
import math
import re
import threading
from types import MappingProxyType

from fluent.runtime import FluentBundle, FluentResource
from fluent.syntax.ast import Junk
from babel.core import UnknownLocaleError


class LocalizationError(ValueError):
    """A catalog or a call does not meet the shared message contract."""


def immutable(value):
    if isinstance(value, dict):
        return MappingProxyType({key: immutable(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(immutable(child) for child in value)
    return value


@lru_cache(maxsize=1)
def registry():
    index = json.loads(files('botw_companion').joinpath('locales/registry.json').read_text(encoding='utf-8'))
    try:
        if index['schema'] != 1 or not isinstance(index['locales'], dict) or not isinstance(index['aliases'], dict):
            raise LocalizationError('Invalid locale registry')
        if index['default'] not in index['locales']:
            raise LocalizationError('Invalid default locale')
        for identity, info in index['locales'].items():
            if not re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*', identity) or info['id'] != identity:
                raise LocalizationError('Invalid locale identity')
        if any(not isinstance(alias, str) or identity not in index['locales'] for alias, identity in index['aliases'].items()):
            raise LocalizationError('Invalid locale aliases')
    except (KeyError, TypeError, AttributeError) as error:
        raise LocalizationError('Invalid locale registry') from error
    return immutable(index)


def resolve(value):
    if not isinstance(value, str):
        return None
    try:
        index = registry()
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return index['aliases'].get(value.casefold())


def default_locale():
    try:
        return registry()['default']
    except (OSError, ValueError, KeyError, TypeError):
        # A valid BCP-47 emergency header, never a selectable locale/path.
        return 'und'


@lru_cache(maxsize=1)
def settings():
    return immutable(json.loads(files('botw_companion').joinpath('i18n/settings.json').read_text(encoding='utf-8')))


def locale_info(locale):
    identity = resolve(locale)
    if identity is None:
        raise LocalizationError('Unsupported presentation language')
    return registry()['locales'][identity]


@lru_cache(maxsize=16)
def contracts(locale, revision=None):
    info = locale_info(locale)
    root = files('botw_companion').joinpath('locales', info['id'])
    contract = json.loads(root.joinpath('contract.json').read_text(encoding='utf-8'))
    if not isinstance(contract, dict):
        raise LocalizationError('Invalid localization contract')
    return immutable(contract)


@lru_cache(maxsize=32)
def catalog(locale, revision=None, domain='all'):
    info = locale_info(locale)
    root = files('botw_companion').joinpath('locales', info['id'])
    contract = contracts(locale, revision)
    filenames = {'all': 'messages.ftl', 'browser': 'browser.ftl', 'backend': 'backend.ftl'}
    if domain not in filenames:
        raise LocalizationError('Invalid message domain')
    if domain != 'all':
        contract = {key: entry for key, entry in contract.items()
                    if entry.get('browser', True) == (domain == 'browser')}
    try:
        # Callers provide bidi isolation; the formatter must not insert marks.
        bundle = FluentBundle([info['format_locale']], use_isolating=False)
    except (UnknownLocaleError, ValueError, TypeError) as error:
        raise LocalizationError('Invalid formatting locale') from error
    resource = FluentResource(root.joinpath(filenames[domain]).read_text(encoding='utf-8'))
    if any(isinstance(item, Junk) for item in resource.body):
        raise LocalizationError('Malformed localization catalog')
    bundle.add_resource(resource)
    if any(not bundle.has_message(identity) for identity in contract):
        raise LocalizationError('Incomplete localization catalog')
    return bundle, immutable(contract), threading.RLock()


def message(identity, locale=None, **values):
    # Callers own HTML escaping and bidi isolation of the returned text.
    locale = resolve(locale) or default_locale()
    revision = locale_info(locale)['revision']
    expected = contracts(locale, revision).get(identity)
    if expected is None or set(values) != set(expected['params']):
        raise LocalizationError(f'Invalid message or parameters: {identity}')
    domain = 'browser' if expected.get('browser', True) else 'backend'
    bundle, contract, lock = catalog(locale, revision, domain)
    if any(not isinstance(value, (str, int, float)) or isinstance(value, bool) for value in values.values()):
        raise LocalizationError(f'Invalid parameter type: {identity}')
    if any(isinstance(value, float) and not math.isfinite(value) for value in values.values()):
        raise LocalizationError(f'Invalid numeric parameter: {identity}')
    with lock:
        item = bundle.get_message(identity)
        result, errors = bundle.format_pattern(item.value, values)
    if errors:
        raise LocalizationError(f'Cannot format message: {identity}: {errors}')
    return result


def resource_errors():
    # Native package self-tests use the same resource checks as source audits.
    try:
        for locale in registry()['locales']:
            root = files('botw_companion').joinpath('locales', locale)
            for name in ('messages.ftl', 'browser.ftl', 'backend.ftl', 'contract.json', 'browser.js', 'index.html', 'presentation-data.json'):
                if not root.joinpath(name).is_file():
                    raise LocalizationError(f'Missing locale resource: {locale}/{name}')
            json.loads(root.joinpath('contract.json').read_text(encoding='utf-8'))
            json.loads(root.joinpath('presentation-data.json').read_text(encoding='utf-8'))
            resource = FluentResource(root.joinpath('messages.ftl').read_text(encoding='utf-8'))
            if any(isinstance(item, Junk) for item in resource.body):
                raise LocalizationError('Malformed localization catalog')
            for domain in ('all', 'browser', 'backend'):
                catalog(locale, locale_info(locale)['revision'], domain)
        return []
    except (OSError, ValueError, KeyError, TypeError) as error:
        return [f'Invalid localization resources: {error}']


def locale_resource(name, locale):
    # The server must allowlist public assets before calling this resolver.
    identity = resolve(locale) or default_locale()
    if name in {'index.html', 'locale.js'}:
        return files('botw_companion').joinpath('locales', identity,
                                             'index.html' if name == 'index.html' else 'browser.js')
    return files('botw_companion.web').joinpath(*name.split('/'))


def download_header(value, locale):
    from urllib.parse import quote
    names = {'attachment; filename=botw-companion-suivi-manuel.json': 'export-manual',
             'attachment; filename=botw-companion-itineraires.json': 'export-routes',
             'attachment; filename=botw-companion-sauvegarde.json': 'export-backup'}
    if value not in names:
        return value
    try:
        filename = message(names[value], locale)
    except (OSError, ValueError, KeyError, TypeError):
        return value
    validate_download_name(filename)
    if filename.isascii() and all(c.isalnum() or c in '-_.' for c in filename):
        return 'attachment; filename=' + filename
    return "attachment; filename=botw-companion-export.json; filename*=UTF-8''" + quote(filename, safe='')


def validate_download_name(filename):
    if (not isinstance(filename, str) or not filename.endswith('.json')
            or any(c in '/\\' or ord(c) < 32 or ord(c) == 127 for c in filename)):
        raise LocalizationError('Invalid suggested download name')
