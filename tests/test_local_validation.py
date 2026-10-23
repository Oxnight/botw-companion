from pathlib import Path
import os
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import validate_local as validation


class LocalValidationTests(unittest.TestCase):
    def test_checks_use_existing_tools_and_keep_strict_resource_validation(self):
        with patch.object(validation, 'run') as run, patch.object(validation.shutil, 'which', return_value='/tool/actionlint'):
            validation.checks({"PATH": ""})
        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn([validation.sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], commands)
        self.assertIn([validation.sys.executable, 'tools/i18n.py', 'check'], commands)
        self.assertTrue(any(command[:2] == ['node', '--test'] and len(command) > 2 for command in commands))
        workflow = (validation.ROOT / '.github/workflows/release.yml').read_text()
        for tool in ('release_metadata.py', 'check_version_consistency.py', 'audit_distribution.py', 'audit_localization.py'):
            self.assertIn('tools/' + tool, workflow)
            self.assertIn([validation.sys.executable, 'tools/' + tool], commands)
        self.assertEqual(commands[-1], ['git', 'diff', '--check'])

    def test_command_failure_stops_validation_and_preserves_exit_code(self):
        failure = subprocess.CalledProcessError(17, ['synthetic-check'])
        with patch.object(validation, 'run', side_effect=failure) as run:
            self.assertEqual(validation.main(['--phase', 'checks']), 17)
        self.assertEqual(run.call_count, 1)

    def test_child_environment_preserves_parent_and_uses_current_python(self):
        before = dict(os.environ)
        child = validation.environment()
        self.assertEqual(dict(os.environ), before)
        self.assertEqual(child.get('HOME'), before.get('HOME'))
        self.assertEqual(child.get('USERPROFILE'), before.get('USERPROFILE'))
        self.assertEqual(child['GIT_OPTIONAL_LOCKS'], '0')
        self.assertEqual(child['PATH'].split(os.pathsep)[0], str(Path(validation.sys.executable).parent))

    def test_native_platform_selection_rejects_wrong_architecture(self):
        with patch.object(validation.platform, 'machine', return_value='arm64'), patch.object(validation.platform, 'mac_ver', return_value=('27.0', (), '')):
            validation.check_platform('darwin')
            with self.assertRaises(ValueError):
                validation.check_platform('win32')
        with patch.object(validation.platform, 'machine', return_value='AMD64'):
            validation.check_platform('win32')
            with self.assertRaises(ValueError):
                validation.check_platform('linux')

    def test_browser_entry_points_reuse_workflow_helpers(self):
        with patch.object(validation, 'check_platform'), patch.object(validation, 'run') as run:
            validation.browsers({}, 'darwin', validation.ROOT / 'test-results/output')
            self.assertEqual(run.call_args.args[0], ['bash', 'tools/run_browser_smoke.sh', str(validation.ROOT / 'test-results/output/browser-logs')])
            validation.browsers({}, 'win32', validation.ROOT / 'test-results/output')
            command = run.call_args.args[0]
            self.assertEqual(command[:3], ['pwsh', '-NoProfile', '-Command'])
            self.assertTrue(command[3].startswith("$ErrorActionPreference = 'Stop';"))
            for browser in ('chrome', 'edge', 'firefox', 'chromium', 'webkit'):
                self.assertIn("'" + browser + "'", command[3])
        workflow = (validation.ROOT / '.github/workflows/release.yml').read_text()
        self.assertIn('bash tools/run_browser_smoke.sh', workflow)
        self.assertIn('./tools/run_browser_smoke.ps1', workflow)

    def test_missing_published_reference_never_selects_bootstrap(self):
        with self.assertRaisesRegex(ValueError, 'published upgrade'):
            validation.reference_paths({'upgrade_tag': 'v1.0.0', 'minimum_upgrade_tag': ''}, None, None)
        with tempfile.TemporaryDirectory() as temporary:
            previous = Path(temporary) / 'reference.dmg'
            previous.write_bytes(b'synthetic package')
            with self.assertRaisesRegex(ValueError, 'published minimum_upgrade'):
                validation.reference_paths({'upgrade_tag': 'v1.1.0', 'minimum_upgrade_tag': 'v1.0.0'}, previous, None)
            self.assertEqual(validation.reference_paths({'upgrade_tag': '', 'minimum_upgrade_tag': ''}, None, None), [])

    def test_source_copy_includes_new_files_without_exporting_git_or_local_agents(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / 'checkout'
            root.mkdir()
            (root / 'source.py').write_text('print(1)\n')
            (root / 'new.py').write_text('print(2)\n')
            (root / 'AGENTS.md').write_text('local\n')
            target = Path(temporary) / 'export'
            result = subprocess.CompletedProcess([], 0, stdout=b'source.py\0new.py\0AGENTS.md\0')
            with patch.object(validation, 'ROOT', root), patch.object(validation.subprocess, 'run', return_value=result) as run:
                validation.source_copy(target, {'GIT_OPTIONAL_LOCKS': '0'})
            self.assertEqual(sorted(path.name for path in target.iterdir()), ['new.py', 'source.py'])
            self.assertEqual(run.call_args.args[0], ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'])

    def test_native_packages_reuse_build_and_full_installation_checks_in_isolation(self):
        metadata = {'upgrade_tag': 'v1.1.0', 'minimum_upgrade_tag': 'v1.0.0',
                    'dmg_name': 'candidate.dmg', 'installer_name': 'candidate.exe'}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            previous, minimum = root / 'previous', root / 'minimum'
            previous.write_bytes(b'previous package')
            minimum.write_bytes(b'minimum package')
            for system in ('darwin', 'win32'):
                output = root / system
                output.mkdir()
                def copy_source(destination, env):
                    destination.mkdir()
                completed = subprocess.CompletedProcess([], 0, stdout=json.dumps(metadata).encode())
                with patch.object(validation, 'check_platform'), patch.object(validation, 'source_copy', side_effect=copy_source), \
                     patch.object(validation.subprocess, 'run', return_value=completed), patch.object(validation, 'run') as run:
                    validation.packages({'HOME': 'parent-home'}, system, output, previous, minimum)
                self.assertEqual(run.call_count, 3)
                build, latest, oldest = run.call_args_list
                platform_name = 'macos' if system == 'darwin' else 'windows'
                self.assertIn('tools/build_' + platform_name + '_app.' + ('sh' if system == 'darwin' else 'ps1'), build.args[0])
                self.assertIn('tools/test_' + platform_name + '_installation.' + ('sh' if system == 'darwin' else 'ps1'), latest.args[0])
                self.assertEqual(latest.args[0][-1], str(previous))
                self.assertEqual(oldest.args[0][-1], str(minimum))
                for call in run.call_args_list:
                    self.assertEqual(call.kwargs['cwd'], output / 'source')
                    self.assertEqual(call.kwargs['environment']['HOME'], 'parent-home')
                    self.assertEqual(call.kwargs['environment']['RUNNER_TEMP'], str(output / 'native-temp'))
                self.assertTrue((output / 'native-temp').is_dir())
