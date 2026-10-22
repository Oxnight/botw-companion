#!/usr/bin/env python3
"""Install and verify a built wheel outside the checkout, without a network."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import venv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheel', type=Path)
    parser.add_argument('--wheelhouse', type=Path, required=True)
    args = parser.parse_args()
    wheel, wheelhouse = args.wheel.resolve(strict=True), args.wheelhouse.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='botw-wheel-') as directory:
        root = Path(directory)
        venv.EnvBuilder(with_pip=True).create(root / 'environment')
        python = root / 'environment' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        environment = {key: value for key, value in os.environ.items() if key not in {'PYTHONPATH', 'PYTHONHOME'}}
        subprocess.run([str(python), '-I', '-m', 'pip', 'install', '--no-index', '--find-links', str(wheelhouse), str(wheel)], cwd=root, env=environment, check=True)
        script = '''import json
from pathlib import Path
import botw_companion
from botw_companion.i18n import registry, message, locale_resource
from botw_companion.i18n.presentation import present
from botw_companion.offline_runtime import offline_resource_errors, remote_runtime_dependencies
assert Path(botw_companion.__file__).resolve().is_relative_to(Path.cwd().resolve())
assert not offline_resource_errors(), offline_resource_errors()
assert not remote_runtime_dependencies()
for locale in registry()['locales']:
    assert message('inactive-tab-title', locale)
    assert locale_resource('index.html', locale).is_file()
    assert present({'label': 'Sanctuaires', 'note_personnelle': 'Sanctuaires'}, locale)['note_personnelle'] == 'Sanctuaires'
print(json.dumps({'isolated_wheel_locales': list(registry()['locales']), 'resources': 'passed'}))
'''
        subprocess.run([str(python), '-I', '-c', script], cwd=root, env=environment, check=True)


if __name__ == '__main__':
    main()
