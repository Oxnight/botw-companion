#!/usr/bin/env python3
"""Reproduce the one-time English prose/term import from the reviewed sources.

This development importer does not register a locale or generate application
logic. Its output directory must be new; it never overwrites a working catalog.
"""
from __future__ import annotations

import argparse
from collections import defaultdict, Counter
import hashlib
import json
from pathlib import Path
import re
import sys

from fluent.syntax import ast, FluentSerializer
from fluent.runtime import FluentBundle, FluentResource

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from botw_companion.i18n.presentation import Presenter, TECHNICAL_VALUE


SOURCE_DIGESTS = {'localization_en.json': 'f3bc5db0063b291b214e67ea3c40fce349770b67b7267317ff8fcf60b0dc0b1d', 'localization_en_ui.json': '2e707f6174ce4ab77a0e736554500ab240d3f07bda27abb13d55ffbd9c2f6bb1'}

FRENCH_DIGESTS = {'catalog_fr_compiled.json': '3f9b3d8261ec885a00b3d732f17e785914659a52380c7604e59d5a5aae0485b1', 'cartography_reference_fr_compiled.json': 'f1dcd0615341a731ba21c6b61a438eb24310ee80ebc9545ced14cf1eb4feec95', 'nomenclature_fr_reference.json': '448a702018789df6714719e010ec1468f518cfbaedc59800e24eaea3fbcf18b1'}

def text_pattern(value):
    nodes = []
    for chunk in re.split(r'(ZXQ\d+QXZ)', value):
        if re.fullmatch(r'ZXQ\d+QXZ', chunk):
            nodes.append(ast.Placeable(ast.VariableReference(ast.Identifier('value' + chunk[3:-3]))))
        elif chunk:
            escaped = ''.join('\\u%04X' % ord(c) if ord(c) < 32 else '\\' + c if c in '\\"' else c for c in chunk)
            nodes.append(ast.Placeable(ast.StringLiteral(escaped)))
    return ast.Pattern(nodes)


def formatter(messages):
    bundle = FluentBundle(['en-US'], use_isolating=False)
    bundle.add_resource(FluentResource(messages))
    def render(identity, _locale, **values):
        value, errors = bundle.format_pattern(bundle.get_message(identity).value, values)
        if errors:
            raise ValueError(f'Cannot import {identity}: {errors}')
        return value
    return render


def complete_cache_inputs(reference, strings, glossary, rules, diagnostic_messages):
    original = {**reference['compiled_strings'], **strings}
    retired = {key: value for key, value in original.items()
               if TECHNICAL_VALUE.fullmatch(key) and key != value}
    expected = {key: key if TECHNICAL_VALUE.fullmatch(key) else value for key, value in original.items()}
    base = {'strings': strings, 'glossary': glossary, 'patterns': rules,
            'names_by_id': reference['names_by_id'], 'trials_by_id': reference['trials_by_id']}
    renderer = Presenter('importer', reference=base, format_message=formatter(diagnostic_messages))
    differences = [(source, target) for source, target in sorted(expected.items())
                   if renderer.translate_text(source) != target]
    # Extract numeric slots only from the pinned output. Bind wording exceptions
    # to their exact source so they cannot affect other messages.
    number = re.compile(r'(?<![\w])[-+]?\d+(?:\.\d+)?(?![\w])')
    def normalized(value):
        index = iter(range(1000))
        return number.sub(lambda match: 'ZXQ' + str(next(index)) + 'QXZ', value)
    groups, static = defaultdict(list), {}
    for source, target in differences:
        values = number.findall(source)
        if values and values == number.findall(target):
            groups[normalized(source)].append((source, target, values, normalized(target)))
        else:
            static[source] = target
    entries, contract, bindings, added_rules = {'fr': [], 'en': []}, {}, {}, []
    counter = 0
    def add(identity, source, target, values):
        indices = list(range(len(values)))
        raw = ['value' + str(i) for i in indices]
        numeric = ['number' + str(i) for i in indices]
        contract[identity] = {'params': raw + numeric, 'required': raw,
                              'rich': False, 'markup': [], 'browser': False}
        if not raw:
            contract[identity].pop('required')
        for locale, value in [('fr', source), ('en', target)]:
            entries[locale].append(ast.Message(ast.Identifier(identity), text_pattern(value)))
        return {**{raw[i]: value for i, value in enumerate(values)},
                **{numeric[i]: float(value) for i, value in enumerate(values)}}
    for source, rows in sorted(groups.items()):
        variants = Counter(row[3] for row in rows)
        majority = sorted(variants, key=lambda value: (-variants[value], value))[0]
        identities = {}
        for target in sorted(variants):
            counter += 1
            identity = 'legacy-template-' + str(counter)
            add(identity, source, target, rows[0][2])
            identities[target] = identity
        indices = list(range(len(rows[0][2])))
        added_rules.append({'source': source, 'message': identities[majority],
                            'preserve_values': indices, 'numeric_values': indices})
        if len(variants) > 1:
            for literal, target, values, variant in rows:
                bindings[literal] = {'message': identities[variant],
                    'values': {**{'value' + str(i): value for i, value in enumerate(values)},
                               **{'number' + str(i): float(value) for i, value in enumerate(values)}}}
    for source, target in sorted(static.items()):
        counter += 1
        identity = 'legacy-bound-' + str(counter)
        add(identity, source, target, [])
        bindings[source] = {'message': identity, 'values': {}}
    def resource(locale):
        return FluentSerializer().serialize(ast.Resource(entries[locale]))
    completed = {**base, 'patterns': added_rules + rules, 'exact_messages': bindings}
    renderer = Presenter('importer', reference=completed,
                         format_message=formatter(diagnostic_messages + resource('en')))
    residual = [(source, target) for source, target in sorted(expected.items())
                if renderer.translate_text(source) != target]
    for source, target in residual:
        values = number.findall(source)
        if values != number.findall(target):
            raise ValueError('Review nonmatching numeric source values: ' + source)
        counter += 1
        identity = 'legacy-bound-' + str(counter)
        parameters = add(identity, normalized(source) if values else source,
                         normalized(target) if values else target, values)
        bindings[source] = {'message': identity, 'values': parameters}
    renderer = Presenter('importer', reference=completed,
                         format_message=formatter(diagnostic_messages + resource('en')))
    failures = [source for source, target in sorted(expected.items()) if renderer.translate_text(source) != target]
    if failures:
        raise ValueError('Imported presentation differs: ' + repr(failures[:5]))
    return {'legacy-patterns.json': added_rules + rules, 'message-bindings.json': bindings,
            'cache-source.json': sorted(reference['compiled_strings']), 'message-contract.json': contract,
            'additional-fr.ftl': resource('fr'), 'additional-en.ftl': resource('en')}, {
                'numeric_templates': len(added_rules), 'additional_messages': len(contract),
                'exact_bindings': len(bindings), 'retired_non_display_cache_values': retired,
                'verification': 'All presentation inputs match; protocol-shaped values are preserved verbatim.'}

def imported(source):
    paths = [source / name for name in ('localization_en.json', 'localization_en_ui.json')]
    for path in paths:
        if hashlib.sha256(path.read_bytes()).hexdigest() != SOURCE_DIGESTS[path.name]:
            raise ValueError('Legacy input differs from the reviewed migration source: ' + path.name)
    reference, curated = [json.loads(path.read_text(encoding='utf-8')) for path in paths]
    strings = {**reference['strings'], **curated['strings']}
    glossary = {**reference['glossary'], **{k: v for k, v in curated['strings'].items() if len(k) >= 4}}
    if not glossary.keys() <= strings.keys():
        raise ValueError('Unexpected legacy glossary keys: review before importing')
    metadata = {'base_commit': '8009763a0623dd660a963a93def8fc2569c42202',
                'sources': {path.name: {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path in paths},
                'source_counts': {role: len(reference[role]) for role in ('strings', 'glossary', 'compiled_strings', 'names_by_id', 'trials_by_id', 'patterns')},
                'curated_counts': {'strings': len(curated['strings']), 'script_overrides': len(curated['script_overrides'])},
                'effective_counts': {'strings': len(strings), 'glossary_members': len(glossary)},
                'shadowed_glossary_values': {key: value for key, value in glossary.items() if strings[key] != value},
                'script_overrides_imported_into_messages': curated['script_overrides'],
                'original_provenance': reference.get('sources', [])}
    entries, patterns = [], []
    for index, rule in enumerate(reference['patterns'], 1):
        identity = 'legacy-diagnostic-' + str(index)
        entries.append(ast.Message(ast.Identifier(identity), text_pattern(rule['target'])))
        patterns.append({'source': rule['source'], 'message': identity, 'preserve_values': rule.get('preserve_values', [])})
    diagnostics = FluentSerializer().serialize(ast.Resource(entries))
    from botw_companion.resources import load_catalog
    canonical_root = Path(__file__).resolve().parents[1] / 'botw_companion/data'
    for name, digest in FRENCH_DIGESTS.items():
        if hashlib.sha256((canonical_root / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Canonical French source differs from the reviewed input: ' + name)
    catalog = load_catalog()
    names = {group + ':' + str(item['id']): item['name']
             for group, items in catalog.items() if isinstance(items, list)
             for item in items if isinstance(item, dict) and item.get('id') and item.get('name')}
    trials = {str(item['id']): item['trial'] for item in catalog['shrines']}
    french_game = {'names_by_id': {key: names[key] for key in reference['names_by_id']},
                   'trials_by_id': {key: trials[key] for key in reference['trials_by_id']}}
    metadata['french_canonical_sources'] = FRENCH_DIGESTS
    completed, statistics = complete_cache_inputs(reference, strings, glossary, patterns, diagnostics)
    metadata['cache_completion'] = statistics
    return {'prose.json': {'strings': strings},
            'game.json': {role: reference[role] for role in ('names_by_id', 'trials_by_id')},
            'legacy-cache.json': {'compiled_strings': reference['compiled_strings']},
            'legacy-glossary.json': sorted(glossary), 'migration.json': metadata,
            'diagnostics.ftl': diagnostics, 'game-fr.json': french_game, **completed}



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-data', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    products = imported(args.source_data)
    args.output.mkdir(parents=True, exist_ok=False)
    for name, value in products.items():
        content = value if name.endswith('.ftl') else json.dumps(value, ensure_ascii=False, indent=2) + '\n'
        (args.output / name).write_bytes(content.encode('utf-8'))


if __name__ == '__main__':
    main()
