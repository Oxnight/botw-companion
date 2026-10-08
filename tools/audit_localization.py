#!/usr/bin/env python3
"""Check hidden UI templates, English prose and stable HTML/API contracts."""
from __future__ import annotations

import ast
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_english_assets import js_value
from botw_companion.english import translate_text
from tools.localization_checks import has_french_prose

DISPLAY_ATTRIBUTES = {'title', 'aria-label', 'placeholder', 'alt'}
FRENCH = re.compile(r'[éèêàùçœ]|\b(?:Carte|Personnel|Filtres|Zoomer|coffre|coffres|sanctuaire|sanctuaires|rejoins|Cinetis|Marmite|Radeau|Bijouterie|Tetralame|référencé|terminé|ajoutée|affichée|positionné)\b')


class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.structure, self.prose = [], []

    def handle_starttag(self, tag, attrs):
        stable = [(key, re.sub(r'ZXQ\d+QXZ', 'EXPRESSION', value or ''))
                  for key, value in attrs if key not in DISPLAY_ATTRIBUTES]
        self.structure.append(('start', tag, stable))
        self.prose.extend(value for key, value in attrs if key in DISPLAY_ATTRIBUTES and value)

    def handle_endtag(self, tag):
        self.structure.append(('end', tag))

    def handle_data(self, value):
        self.prose.append(value)


ERROR_FRENCH = re.compile(r'[éèêàùçœ]|\b(?:introuvable|invalide|Impossible|Aucun|aucun|sauvegarde|uniquement|fichier|Dossier|dossier)\b')


def audit_errors():
    """Inspect complete raised diagnostics, including interpolated values."""
    errors, checked = [], 0
    for path in (ROOT / "botw_companion").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call) or not node.exc.args:
                continue
            argument = node.exc.args[0]
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                value = argument.value
            elif isinstance(argument, ast.JoinedStr):
                value = "".join(part.value if isinstance(part, ast.Constant) else "CHECKVALUE"
                                for part in argument.values)
            else:
                continue
            if not ERROR_FRENCH.search(value):
                continue
            checked += 1
            translated = translate_text(value)
            if has_french_prose(translated):
                errors.append(f"French in diagnostic {path.name}:{node.lineno}: {translated}")
    return checked, errors


def audit():
    source = json.loads(subprocess.check_output(['node', str(ROOT/'tools/extract_ui_strings.cjs')], cwd=ROOT, text=True))
    errors, checked = [], set()
    for entry in source:
        if entry.get('key'):
            continue
        value = entry.get('template', entry['value'])
        if value in checked or value.startswith(('/api/', 'https://', '#', '.')):
            continue
        checked.add(value)
        translated = js_value(value)
        if not ('<' in value and '>' in value):
            if has_french_prose(translated) and not re.fullmatch(r'[a-z0-9_:-]+', translated):
                errors.append('French in English text: ' + translated[:160])
            continue
        french, english = Markup(), Markup()
        french.feed(value)
        english.feed(translated)
        if french.structure != english.structure:
            errors.append('HTML structure changed: ' + value[:160])
        for text in english.prose:
            if has_french_prose(text):
                errors.append('French in English template: ' + text[:160])
    for filename in ('app', 'route_planner'):
        source = (ROOT/f'botw_companion/web/{filename}.js').read_text()
        english = (ROOT/f'botw_companion/web/{filename}_en.js').read_text()
        paths = r'/api/[A-Za-z0-9_/?=:.+-]*'
        if sorted(re.findall(paths, source)) != sorted(re.findall(paths, english)):
            errors.append('API paths changed in ' + filename)
        original_leaves = json.loads(subprocess.check_output(['node', str(ROOT/'tools/extract_ui_strings.cjs'), f'botw_companion/web/{filename}.js'], cwd=ROOT, text=True))
        english_leaves = json.loads(subprocess.check_output(['node', str(ROOT/'tools/extract_ui_strings.cjs'), f'botw_companion/web/{filename}_en.js'], cwd=ROOT, text=True))
        originals = [e['template'] for e in original_leaves if e.get('quasi') == 0]
        translations = [e['template'] for e in english_leaves if e.get('quasi') == 0]
        if len(originals) != len(translations):
            errors.append('Template structure count changed in ' + filename)
        for first, second in zip(originals, translations):
            if '<' not in first or '>' not in first:
                continue
            a, b = Markup(), Markup()
            a.feed(first)
            b.feed(second)
            if a.structure != b.structure:
                errors.append('Generated HTML structure changed: ' + first[:160])
            errors.extend('French in generated template: '+text[:160] for text in b.prose if has_french_prose(text))
    for filename in ('index_en.html',):
        parsed = Markup()
        parsed.feed((ROOT/'botw_companion/web'/filename).read_text())
        errors.extend('French in English HTML: '+value[:160] for value in parsed.prose if has_french_prose(value))
    diagnostics, diagnostic_errors = audit_errors()
    errors.extend(diagnostic_errors)
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'Localization audit passed: {len(checked)} strings and complete templates; hidden labels, attributes, API paths and {diagnostics} raised diagnostics checked.')


if __name__ == '__main__':
    audit()
