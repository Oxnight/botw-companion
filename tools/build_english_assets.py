#!/usr/bin/env python3
"""Compile offline English browser assets from the canonical French sources."""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from botw_companion.english import translate_text


def plain(value: str) -> str:
    result = translate_text(value)
    if re.search(r"sauvegarde", value, re.I) and not re.search(
        r"générale|personnelles|restaur|import|export|suivi|notes|données", value, re.I
    ):
        result = re.sub(r"\bbackup(s)?\b", lambda m: "save files" if m[1] else "save", result, flags=re.I)
    return result


def markup(value: str) -> str:
    # Translate complete templates so quotes and expressions inside technical
    # attributes never become prose. Preserve every tag and attribute boundary.
    tags = re.compile(r'<!--[\s\S]*?-->|<(?:[^>"\']|"[^"]*"|\'[^\']*\')*>')
    attributes = re.compile(r'((?:aria-label|title|placeholder|alt)\s*=\s*)(["\'])(.*?)(\2)', re.S)
    parts, offset = [], 0
    for match in tags.finditer(value):
        parts.append(html.escape(plain(html.unescape(value[offset:match.start()])), quote=False))
        parts.append(attributes.sub(lambda m: m[1] + m[2] +
            html.escape(plain(html.unescape(m[3])), quote=True) + m[4], match[0]))
        offset = match.end()
    parts.append(html.escape(plain(html.unescape(value[offset:])), quote=False))
    return ''.join(parts)


def js_value(value: str) -> str:
    if value == 'fr-FR': return 'en-US'
    if value == 'fr': return 'en'
    if re.fullmatch(r'[a-z0-9_-]+', value) and value not in {'de', 'guide', 'indisponible'}:
        return value
    if '<' in value or '>' in value:
        return markup(value)
    return plain(value)


def english_morphology(value: str) -> str:
    # French adjectives carry plural suffixes. English adjectives do not;
    # retain the noun suffix once and remove only these known display suffixes.
    suffix = r'\$\{[^{}]*?(?:"s"\s*:\s*""|""\s*:\s*"s")[^{}]*?\}'
    value = re.sub(r'\b(completed|displayed|recorded|added|exclusive|unavailable|retained|remaining|data)(' + suffix + ')', r'\1', value)
    value = re.sub(r'(\b(?:point|objective|completion))(' + suffix + r')\2', r'\1\2', value)
    return value


def outputs():
    inventory = json.loads(subprocess.check_output(['node', str(ROOT / 'tools/extract_ui_strings.cjs')], cwd=ROOT, text=True))
    overrides = json.loads((ROOT / 'botw_companion/data/localization_en_ui.json').read_text())['script_overrides']
    for name in ['app', 'route_planner']:
        relative = 'botw_companion/web/' + name + '.js'
        source = (ROOT / relative).read_text(encoding='utf-8').encode('utf-16-le')
        for entry in sorted((x for x in inventory if x['file'] == relative and not x.get('key')), key=lambda x: x['start'], reverse=True):
            if entry['kind'] == 'template':
                translated_template = js_value(entry['template'])
                markers = re.findall(r'ZXQ\d+QXZ', entry['template'])
                if re.findall(r'ZXQ\d+QXZ', translated_template) != markers:
                    raise ValueError('Translation changed template expression order: ' + entry['template'][:120])
                translated = re.split(r'ZXQ\d+QXZ', translated_template)[entry['quasi']]
            else:
                translated = js_value(entry['value'])
            if entry['kind'] == 'literal':
                replacement = json.dumps(translated, ensure_ascii=False)
            else:
                replacement = translated.replace('\\', '\\\\').replace('`', '\\`').replace('${', '\\${')
            source = source[:entry['start'] * 2] + replacement.encode('utf-16-le') + source[entry['end'] * 2:]
        result = source.decode('utf-16-le')
        for old, new in overrides.items(): result = result.replace(old, new)
        result = english_morphology(result)
        yield ROOT / ('botw_companion/web/' + name + '_en.js'), result
    source = (ROOT / 'botw_companion/web/index.html').read_text(encoding='utf-8')
    result = markup(source).replace('<html lang="fr">', '<html lang="en">')
    result = result.replace('/app.js?lang=fr', '/app.js?lang=en').replace('/route_planner.js?lang=fr', '/route_planner.js?lang=en')
    yield ROOT / 'botw_companion/web/index_en.html', result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    errors = []
    for path, content in outputs():
        if args.check:
            if not path.is_file() or path.read_text(encoding='utf-8') != content: errors.append(path.name)
        else: path.write_text(content, encoding='utf-8')
    if errors: raise SystemExit('English assets need rebuilding: ' + ', '.join(errors))
    print('English assets are consistent.' if args.check else 'English assets built.')


if __name__ == '__main__': main()
