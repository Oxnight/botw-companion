#!/usr/bin/env python3
"""Audit enabled catalogs, hidden messages and application diagnostics."""
from __future__ import annotations

import ast
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from botw_companion.i18n.presentation import translate_text
from tools.i18n import build
from tools.localization_checks import has_french_prose

ERROR_FRENCH = re.compile(r'[éèêàùçœ]|\b(?:introuvable|invalide|Impossible|Aucun|aucun|sauvegarde|uniquement|fichier|Dossier|dossier)\b')


def audit_errors():
    errors, checked = [], 0
    for path in (ROOT / 'botw_companion').rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call) or not node.exc.args:
                continue
            argument = node.exc.args[0]
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                value = argument.value
            elif isinstance(argument, ast.JoinedStr):
                value = ''.join(part.value if isinstance(part, ast.Constant) else 'CHECKVALUE' for part in argument.values)
            else:
                continue
            if ERROR_FRENCH.search(value):
                checked += 1
                translated = translate_text(value, 'en')
                if has_french_prose(translated):
                    errors.append(f'French diagnostic {path.name}:{node.lineno}: {translated}')
    return checked, errors


def audit():
    build(ROOT, check=True)
    subprocess.run(['node', str(ROOT / 'tools/check_i18n_calls.cjs')], cwd=ROOT, check=True)
    subprocess.run(['node', '--test', str(ROOT / 'tests/i18n_compatibility.cjs'),
                    str(ROOT / 'tests/i18n_runtime.cjs')], cwd=ROOT, check=True)
    subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests',
                    '-p', 'test_i18n_compatibility.py'], cwd=ROOT, check=True)
    checked, errors = audit_errors()
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'Localization audit passed: all enabled catalogs, source-owned markup, complete FR/EN symbolic UI, API contracts and {checked} raised diagnostics.')


if __name__ == '__main__':
    audit()
