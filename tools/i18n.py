#!/usr/bin/env python3
"""Scaffold, build, check and measure trusted offline locale resources."""
from __future__ import annotations

import argparse
import copy
from functools import lru_cache
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import sys

from fluent.syntax import FluentParser, FluentSerializer, ast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MANIFEST_FIELDS = {'schema', 'id', 'native_name', 'format_locale', 'direction', 'aliases', 'fallback', 'enabled'}
IDENTITY = re.compile(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z')
TAG = re.compile(r'[a-zA-Z]{2,8}(?:-[a-zA-Z0-9]{1,8})*\Z')


def read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'Duplicate JSON key: {key}')
            result[key] = value
        return result
    try:
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique)
    except ValueError as error:
        raise ValueError(f'{path}: {error}') from error


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def walk(value):
    if isinstance(value, ast.BaseNode):
        yield value
        for child in vars(value).values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def parse_messages(path, contract):
    tree = FluentParser().parse(path.read_text(encoding='utf-8'))
    entries = {}
    for item in tree.body:
        if isinstance(item, ast.Junk):
            raise ValueError(f'{path}: malformed Fluent: {item.annotations}')
        if isinstance(item, (ast.Comment, ast.GroupComment, ast.ResourceComment)):
            continue
        if not isinstance(item, ast.Message) or item.attributes or item.value is None:
            raise ValueError(f'{path}: use value messages without attributes or terms')
        name = item.id.name
        if name in entries or name not in contract:
            raise ValueError(f'{path}: duplicate or unknown message {name}')
        nodes = list(walk(item.value))
        if not any(isinstance(n, ast.VariableReference) or
                   isinstance(n, ast.TextElement) and n.value.strip() or
                   isinstance(n, ast.StringLiteral) and n.parse()['value'].strip()
                   for n in nodes):
            raise ValueError(f'{path}: {name}: empty message')
        variables = {n.id.name for n in nodes if isinstance(n, ast.VariableReference)}
        expected = set(contract[name]['params'])
        required = set(contract[name].get('required', expected))
        if not required <= variables or not variables <= expected:
            raise ValueError(f'{path}: {name}: variables {sorted(variables)}, required {sorted(required)}, allowed {sorted(expected)}')
        # References could bypass this message's parameter and rich-text checks.
        if any(isinstance(n, (ast.MessageReference, ast.TermReference)) for n in nodes):
            raise ValueError(f'{path}: {name}: references are outside the message contract')
        for n in nodes:
            if isinstance(n, ast.FunctionReference) and n.id.name != 'NUMBER':
                raise ValueError(f'{path}: {name}: unsupported function {n.id.name}')
            if isinstance(n, ast.FunctionReference):
                allowed = {'useGrouping', 'minimumIntegerDigits', 'minimumFractionDigits',
                           'maximumFractionDigits', 'minimumSignificantDigits', 'maximumSignificantDigits'}
                if len(n.arguments.positional) != 1 or any(option.name.name not in allowed for option in n.arguments.named):
                    raise ValueError(f'{path}: {name}: unsupported NUMBER options')
                options = {}
                for option in n.arguments.named:
                    key = option.name.name
                    if not isinstance(option.value, ast.NumberLiteral):
                        raise ValueError(f'{path}: {name}: {key} requires an integer')
                    value = float(option.value.value)
                    low, high = ((0, 1) if key == 'useGrouping' else (0, 20)
                                 if key.endswith('FractionDigits') else (1, 21))
                    if not value.is_integer() or not low <= value <= high:
                        raise ValueError(f'{path}: {name}: invalid {key} range')
                    options[key] = value
                for suffix in ('FractionDigits', 'SignificantDigits'):
                    minimum, maximum = options.get('minimum' + suffix), options.get('maximum' + suffix)
                    if minimum is not None and maximum is not None and minimum > maximum:
                        raise ValueError(f'{path}: {name}: inverted NUMBER precision')
        markup = contract[name].get('markup', [])
        found = [n.id.name for n in nodes if isinstance(n, ast.VariableReference) and n.id.name in markup]
        if found != markup:
            raise ValueError(f'{path}: {name}: source-owned markup order changed')
        entries[name] = item
    missing = contract.keys() - entries.keys()
    if missing:
        raise ValueError(f'{path}: missing messages: {", ".join(sorted(missing)[:12])}')
    return tree


def manifests(package):
    settings = read(package / 'i18n/settings.json')
    index = {'schema': 1, 'default': settings['default'], 'locales': {}, 'aliases': {}}
    all_locales = {}
    for path in sorted((package / 'locales').glob('*/locale.json')):
        item = read(path)
        if not MANIFEST_FIELDS <= item.keys() or item.keys() - MANIFEST_FIELDS - {'display_names'} or item['schema'] != 1:
            raise ValueError(f'{path}: unsupported manifest schema/fields')
        identity = item['id']
        if not isinstance(identity, str) or not IDENTITY.fullmatch(identity) or identity != path.parent.name:
            raise ValueError(f'{path}: unsafe or mismatched locale ID')
        if identity in all_locales or not isinstance(item['enabled'], bool):
            raise ValueError(f'{path}: duplicate ID or invalid enabled state')
        if not isinstance(item['native_name'], str) or not item['native_name'].strip() or any(ord(c) < 32 for c in item['native_name']):
            raise ValueError(f'{path}: invalid native name')
        if not isinstance(item['format_locale'], str) or not TAG.fullmatch(item['format_locale']) or item['direction'] not in ('ltr', 'rtl'):
            raise ValueError(f'{path}: invalid formatting tag or direction')
        from babel import Locale
        from babel.core import UnknownLocaleError
        try:
            Locale.parse(item['format_locale'], sep='-')
        except (ValueError, UnknownLocaleError) as error:
            raise ValueError(f'{path}: unsupported formatting locale {item["format_locale"]}') from error
        if not isinstance(item['aliases'], list) or not all(isinstance(x, str) and TAG.fullmatch(x) for x in item['aliases']):
            raise ValueError(f'{path}: invalid aliases')
        labels = item.get('display_names', {})
        if not isinstance(labels, dict) or any(not IDENTITY.fullmatch(key) or not isinstance(value, str) or not value.strip()
                                               for key, value in labels.items()):
            raise ValueError(f'{path}: invalid language display names')
        if item['fallback'] is not None and not isinstance(item['fallback'], str):
            raise ValueError(f'{path}: invalid fallback')
        all_locales[identity] = item
    aliases = {}
    for identity, item in all_locales.items():
        for alias in [identity, *item['aliases']]:
            key = alias.casefold()
            if key in aliases:
                raise ValueError(f'Ambiguous locale alias: {alias}')
            aliases[key] = identity
        seen = {identity}
        current = item['fallback']
        while current is not None:
            if current not in all_locales or current in seen:
                raise ValueError(f'Invalid fallback chain for {identity}: {current}')
            seen.add(current)
            current = all_locales[current]['fallback']
        if item['enabled']:
            index['locales'][identity] = item
    if index['default'] not in index['locales']:
        raise ValueError('Default locale must be enabled')
    index['locales'] = {index['default']: index['locales'][index['default']],
                        **{key: value for key, value in index['locales'].items() if key != index['default']}}
    index['aliases'] = {key: value for key, value in aliases.items() if value in index['locales']}
    common = [package / 'i18n' / name for name in ('contract.json', 'legacy-patterns.json', 'legacy-glossary.json',
                                                'cache-source.json', 'message-bindings.json')]
    for identity, item in index['locales'].items():
        folder = package / 'locales' / identity
        inputs = [folder / name for name in ('locale.json', 'messages.ftl', 'prose.json', 'game.json')]
        item['revision'] = hashlib.sha256(b'\0'.join(path.read_bytes() for path in [*common, *inputs])).hexdigest()
    return index


@lru_cache(maxsize=4)
def compiled_cache(format_locale, serialized_reference, source_keys, messages):
    # Rebuild expanded values from translations, not a locale-supplied cache.
    from fluent.runtime import FluentBundle, FluentResource
    from botw_companion.i18n.presentation import Presenter
    bundle = FluentBundle([format_locale], use_isolating=False)
    bundle.add_resource(FluentResource(messages))

    def render(identity, _locale, **values):
        result, errors = bundle.format_pattern(bundle.get_message(identity).value, values)
        if errors:
            raise ValueError(f'Cannot compile {identity}: {errors}')
        return result

    presenter = Presenter('compiler', reference=json.loads(serialized_reference), format_message=render)
    return {value: presenter.translate_text(value) for value in source_keys}


def outputs(root):
    package = root / 'botw_companion'
    contract = read(package / 'i18n/contract.json')
    index = manifests(package)
    default = index['default']
    expected_prose = read(package / 'locales' / default / 'prose.json')
    expected_game = read(package / 'locales' / default / 'game.json')
    patterns = read(package / 'i18n/legacy-patterns.json')
    bindings = read(package / 'i18n/message-bindings.json')
    source_keys = tuple(read(package / 'i18n/cache-source.json'))
    source_locale = read(package / 'i18n/settings.json')['source_locale']
    html_contract = read(package / 'i18n/html.json')
    template = (package / 'web/index.template.html').read_text(encoding='utf-8')
    yield package / 'locales/registry.json', encoded(index)
    for identity, info in index['locales'].items():
        folder = package / 'locales' / identity
        tree = parse_messages(folder / 'messages.ftl', contract)
        prose, game = read(folder / 'prose.json'), read(folder / 'game.json')
        for label, expected, actual in [('prose', expected_prose, prose), ('game', expected_game, game)]:
            if actual.keys() != expected.keys():
                raise ValueError(f'{folder}/{label}.json: invalid sections')
            for section, keys in expected.items():
                if actual[section].keys() != keys.keys() or any(not isinstance(v, str) or not v.strip() for v in actual[section].values()):
                    missing = keys.keys() - actual[section].keys()
                    raise ValueError(f'{folder}/{label}.json: incomplete {section}; missing {sorted(missing)[:8]}')
        if (folder / 'legacy-cache.json').exists():
            raise ValueError(f'{folder}: expanded caches are generated; remove the obsolete legacy-cache input')
        glossary = {key: prose['strings'][key] for key in read(package / 'i18n/legacy-glossary.json')}
        presentation = {**prose, 'glossary': glossary, **game, 'patterns': patterns}
        if identity != source_locale:
            compiler_input = {**presentation, 'exact_messages': bindings}
            presentation['compiled_strings'] = compiled_cache(info['format_locale'],
                json.dumps(compiler_input, ensure_ascii=False, sort_keys=True, separators=(',', ':')),
                source_keys, (folder / 'messages.ftl').read_text(encoding='utf-8'))
        yield folder / 'presentation-data.json', encoded(presentation)
        yield folder / 'contract.json', encoded(contract)
        for domain in ('browser', 'backend'):
            selected = [entry for entry in tree.body if isinstance(entry, ast.Message)
                        and contract[entry.id.name].get('browser', True) == (domain == 'browser')]
            yield folder / (domain + '.ftl'), FluentSerializer().serialize(ast.Resource(selected))
        from fluent.runtime import FluentBundle, FluentResource
        bundle = FluentBundle([info['format_locale']], use_isolating=False)
        bundle.add_resource(FluentResource((folder / 'messages.ftl').read_text(encoding='utf-8')))
        from botw_companion.i18n import validate_download_name
        for key, entry in contract.items():
            if entry.get('download_name'):
                filename, errors = bundle.format_pattern(bundle.get_message(key).value, {})
                if errors:
                    raise ValueError(f'{folder}: invalid download name {key}')
                try:
                    validate_download_name(filename)
                except ValueError as error:
                    raise ValueError(f'{folder}/messages.ftl: {key}: {error}') from error
        document = template
        for key, context in html_contract.items():
            text, errors = bundle.format_pattern(bundle.get_message(key).value, {})
            if errors:
                raise ValueError(f'{folder}: HTML message {key}: {errors}')
            document = document.replace('__I18N_' + key + '__', html.escape(text, quote=context['kind'] == 'attribute'))
        document = document.replace('<html lang="fr">', f'<html lang="{identity}"' + (' dir="rtl"' if info['direction'] == 'rtl' else '') + '>')
        if info['direction'] == 'rtl':
            # Text direction must not reverse game-space or numeric widgets.
            containment = '<style>html[dir="rtl"] #mapStage,html[dir="rtl"] .coords,html[dir="rtl"] input[type="number"]{direction:ltr;unicode-bidi:isolate}</style>'
            document = document.replace('</head>', '    ' + containment + '\n</head>')
        document = document.replace('    <script src="/language.js"></script>', f'    <script src="/locale.js?lang={identity}"></script>\n    <script src="/i18n.js"></script>\n    <script src="/language.js"></script>')
        document = document.replace('?lang=fr', '?lang=' + identity)
        options = ''.join('<option value="' + key + '">' + html.escape(value.get('display_names', {}).get(identity, value['native_name'])) + '</option>' for key, value in index['locales'].items())
        document, count = re.subn(r'(<select id="languageSelect"[^>]*>).*?(</select>)', lambda m: m[1] + options + m[2], document, flags=re.S)
        if count != 1:
            raise ValueError('Language selector contract changed')
        yield folder / 'index.html', document
        # Escape translator-owned literals, preserving only code-owned slots.
        browser_contract = {key: value for key, value in contract.items() if value.get('browser', True)}
        browser_tree = copy.deepcopy(ast.Resource([entry for entry in tree.body
            if isinstance(entry, ast.Message) and entry.id.name in browser_contract]))
        for entry in browser_tree.body:
            if not isinstance(entry, ast.Message) or not contract[entry.id.name]['rich']:
                continue
            for node in walk(entry.value):
                if isinstance(node, ast.TextElement):
                    node.value = html.escape(node.value, quote=True)
                elif isinstance(node, ast.StringLiteral):
                    raw = node.parse()['value']
                    escaped = html.escape(raw, quote=True)
                    node.value = ''.join('\\u%04X' % ord(c) if ord(c) < 32 else '\\' + c if c in '\\"' else c for c in escaped)
        resource = {'locale': info, 'registry': index,
                    'contract': {key: {'params': value['params']} for key, value in browser_contract.items()},
                    'messages': FluentSerializer().serialize(browser_tree)}
        content = '/* Generated by tools/i18n.py; no application logic. */\nglobalThis.BOTWLocaleData = ' + json.dumps(resource, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029') + ';\n'
        yield folder / 'browser.js', content
    entry = root / 'tools/i18n_browser.js'
    if entry.is_file():
        result = subprocess.run(['node', str(root / 'tools/bundle_i18n.cjs')], cwd=root, capture_output=True, check=True)
        yield package / 'web/i18n.js', result.stdout.decode('utf-8')


def build(root, check=False):
    pending = list(outputs(root))
    stale = []
    for path, content in pending:
        if check:
            if not path.is_file() or path.read_bytes() != content.encode('utf-8'):
                stale.append(str(path.relative_to(root)))
        else:
            path.write_bytes(content.encode('utf-8'))
    if stale:
        raise ValueError('Stale localization output: ' + ', '.join(stale))
    return pending


def scaffold(root, identity, name, formatting, direction):
    if not IDENTITY.fullmatch(identity):
        raise ValueError('Invalid locale ID')
    package = root / 'botw_companion'
    index = manifests(package)
    target = package / 'locales' / identity
    target.mkdir(exist_ok=False)
    source = package / 'locales' / index['default']
    manifest = {'schema': 1, 'id': identity, 'native_name': name, 'format_locale': formatting, 'direction': direction, 'aliases': [], 'fallback': None, 'enabled': False}
    (target / 'locale.json').write_bytes(encoded(manifest).encode('utf-8'))
    # Leave drafts incomplete so scaffolding cannot count as a translation.
    (target / 'messages.ftl').write_bytes(b'# Draft: copy IDs from i18n/contract.json; translate complete messages.\n')
    for filename in ('prose.json', 'game.json'):
        expected = read(source / filename)
        (target / filename).write_bytes(encoded({section: {} for section in expected}).encode('utf-8'))
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('scaffold', 'build', 'check', 'coverage'))
    parser.add_argument('locale', nargs='?')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--name')
    parser.add_argument('--format-locale')
    parser.add_argument('--direction', choices=('ltr', 'rtl'), default='ltr')
    args = parser.parse_args(argv)
    try:
        if args.action == 'scaffold':
            if not all((args.locale, args.name, args.format_locale)):
                parser.error('scaffold requires locale, --name and --format-locale')
            print(scaffold(args.root, args.locale, args.name, args.format_locale, args.direction).relative_to(args.root))
        elif args.action == 'coverage':
            package = args.root / 'botw_companion'
            index = manifests(package)
            contract = read(package / 'i18n/contract.json')
            for folder in sorted((package / 'locales').glob('*/locale.json')):
                info = read(folder)
                tree = FluentParser().parse((folder.parent / 'messages.ftl').read_text(encoding='utf-8'))
                supplied = {n.id.name for n in tree.body if isinstance(n, ast.Message) and n.value}
                counts = {name: {section: len(values) for section, values in read(folder.parent / name).items()} for name in ('prose.json', 'game.json')}
                print(encoded({'locale': info['id'], 'enabled': info['id'] in index['locales'], 'messages': len(supplied & contract.keys()), 'required_messages': len(contract), 'resources': counts, 'fallback_counted': False}).strip())
        else:
            products = build(args.root, args.action == 'check')
            print(f'Localization {args.action}: {len(products)} deterministic products')
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
