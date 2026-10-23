#!/usr/bin/env python3

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(arguments, *, cwd=ROOT, environment=None):
    print('+ ' + subprocess.list2cmdline([str(value) for value in arguments]), flush=True)
    return subprocess.run(arguments, cwd=cwd, env=environment, check=True)


def environment():
    values = dict(os.environ)
    values.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1',
                  GIT_OPTIONAL_LOCKS='0', MACOSX_DEPLOYMENT_TARGET='14.0')
    values['PATH'] = str(Path(sys.executable).parent) + os.pathsep + values.get('PATH', '')
    return values


def check_platform(system):
    if system == 'darwin':
        if platform.machine() != 'arm64' or int(platform.mac_ver()[0].split('.')[0]) < 15:
            raise ValueError('Native/browser validation requires Apple Silicon and macOS 15 or later.')
    elif system != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise ValueError('Native/browser validation requires macOS arm64 or Windows x64.')


def prepare(env):
    run([sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check', '--quiet',
         '-r', 'requirements-runtime.txt'], environment=env)
    npm = 'npm.cmd' if sys.platform == 'win32' else 'npm'
    npx = 'npx.cmd' if sys.platform == 'win32' else 'npx'
    run([npm, 'ci', '--ignore-scripts'], environment=env)
    run([npx, 'playwright', 'install', 'chromium', 'firefox', 'webkit'], environment=env)


def checks(env):
    for script in ('release_metadata.py', 'check_version_consistency.py', 'audit_distribution.py'):
        run([sys.executable, 'tools/' + script], environment=env)
    run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], environment=env)
    run(['node', '--test', *[str(path.relative_to(ROOT)) for path in sorted((ROOT / 'tests').glob('*.cjs'))]], environment=env)
    run([sys.executable, 'tools/i18n.py', 'check'], environment=env)
    run([sys.executable, 'tools/audit_localization.py'], environment=env)
    if shutil.which('actionlint', path=env['PATH']):
        run(['actionlint', '.github/workflows/release.yml'], environment=env)
    else:
        print('UNEXECUTED: actionlint is not installed.', flush=True)
    run(['git', 'diff', '--check'], environment=env)


def browsers(env, system, output):
    check_platform(system)
    if system == 'darwin':
        run(['bash', 'tools/run_browser_smoke.sh', str(output / 'browser-logs')], environment=env)
    else:
        # Keep CI's installed-browser coverage and also exercise Playwright's engines.
        run(['pwsh', '-NoProfile', '-Command',
             "$ErrorActionPreference = 'Stop'; & './tools/run_browser_smoke.ps1' -Browsers 'chrome','edge','firefox','chromium','webkit'; exit $LASTEXITCODE"], environment=env)


def source_copy(destination, env):
    result = subprocess.run(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
                            cwd=ROOT, env=env, capture_output=True, check=True)
    for name in sorted(set(result.stdout.decode('utf-8').split('\0')) - {'', 'AGENTS.md'}):
        source = ROOT / name
        if source.is_symlink() or not source.resolve().is_relative_to(ROOT):
            raise ValueError('Source export requires a regular file: ' + name)
        if not source.exists():
            continue
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def reference_paths(metadata, previous, minimum):
    references = []
    for prefix, supplied in (('upgrade', previous), ('minimum_upgrade', minimum)):
        if metadata[prefix + '_tag'] and supplied is None:
            raise ValueError('A published ' + prefix + ' package is required: ' + metadata[prefix + '_tag'])
        if supplied is not None:
            path = supplied.resolve(strict=True)
            if not path.is_file():
                raise ValueError('Reference package must be a file: ' + str(path))
            references.append(path)
    return references


def packages(env, system, output, previous=None, minimum=None):
    check_platform(system)
    metadata = json.loads(subprocess.run([sys.executable, 'tools/release_metadata.py'],
                          cwd=ROOT, env=env, capture_output=True, check=True).stdout)
    references = reference_paths(metadata, previous, minimum)
    source = output / 'source'
    if source.exists():
        raise ValueError('Package source destination already exists: ' + str(source))
    source_copy(source, env)
    temporary = output / 'native-temp'
    temporary.mkdir()
    native_env = {**env, 'RUNNER_TEMP': str(temporary)}
    if system == 'darwin':
        run(['bash', 'tools/build_macos_app.sh'], cwd=source, environment=native_env)
        candidate = source / 'dist' / metadata['dmg_name']
        installer = ['bash', 'tools/test_macos_installation.sh', str(candidate)]
    else:
        run(['pwsh', '-NoProfile', '-File', 'tools/build_windows_app.ps1'], cwd=source, environment=native_env)
        candidate = source / 'dist/installer' / metadata['installer_name']
        installer = ['pwsh', '-NoProfile', '-File', 'tools/test_windows_installation.ps1',
                     '-InstallerPath', str(candidate)]
    for reference in references or [None]:
        arguments = list(installer)
        if reference:
            if system == 'win32':
                arguments.append('-PreviousInstallerPath')
            arguments.append(str(reference))
        print('Replacement/recovery validation; a same-version reference is not an upgrade.', flush=True)
        run(arguments, cwd=source, environment=native_env)
    print('Native package retained at: ' + str(candidate), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run local release checks and native validation without publishing.')
    parser.add_argument('--phase', choices=('checks', 'browsers', 'packages', 'all'), default='all')
    parser.add_argument('--prepare', action='store_true', help='Install pinned dependencies and Playwright engines.')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--previous-package', type=Path)
    parser.add_argument('--minimum-package', type=Path)
    args = parser.parse_args(argv)
    output = args.output_dir or ROOT / 'test-results/local-validation' / ('local-run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    env = environment()
    try:
        if args.phase in ('browsers', 'packages', 'all'):
            output = output.resolve()
            if not output.is_relative_to(ROOT / 'test-results'):
                raise ValueError('Validation output must stay in the ignored test-results directory.')
            output.mkdir(parents=True, exist_ok=True)
        if args.prepare:
            prepare(env)
        if args.phase in ('checks', 'all'):
            checks(env)
        if args.phase in ('browsers', 'all'):
            browsers(env, sys.platform, output)
        if args.phase in ('packages', 'all'):
            packages(env, sys.platform, output, args.previous_package, args.minimum_package)
    except subprocess.CalledProcessError as error:
        return error.returncode if error.returncode > 0 else 1
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
