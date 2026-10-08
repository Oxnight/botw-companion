import hashlib
import os
import plistlib
from pathlib import Path
import tempfile
import threading
import subprocess
import sys
import shutil
from dataclasses import replace
import unittest
from unittest.mock import patch

from botw_companion.macos_updates import (
    INSTALL_STATE_NAME,
    MacOSUpdateError,
    MacOSUpdateInstaller,
)
from botw_companion.update_downloads import UpdateInstallCandidate


class FakeProcess:
    def poll(self):
        return None


class MacOSUpdateTests(unittest.TestCase):
    VERSION = "0.40.0-alpha." + "40"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / "updates"
        self.application = self.base / "Applications" / "BOTW Companion.app"
        self.executable = self.application / "Contents" / "MacOS" / "BOTW Companion"
        self.executable.parent.mkdir(parents=True)
        self.executable.write_bytes(b"arm64 app")
        self.helper = self.base / "macos_update_relay.sh"
        self.helper.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
        self.dmg = self.root / f"BOTW_Companion_{self.VERSION}_macOS_arm64.dmg"
        self.dmg.parent.mkdir(parents=True)
        self.dmg.write_bytes(b"verified dmg")
        self.digest = hashlib.sha256(self.dmg.read_bytes()).hexdigest()
        self.metadata = self.root / f"{self.dmg.name}.metadata.json"
        self.metadata.write_text(
            "{" +
            f'"ready": true, "version": "{self.VERSION}", '
            f'"filename": "{self.dmg.name}", "size": {self.dmg.stat().st_size}, '
            f'"digest": "sha256:{self.digest}"' +
            "}",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def candidate(self):
        return UpdateInstallCandidate(
            version=self.VERSION,
            installer=self.dmg,
            size=self.dmg.stat().st_size,
            digest=self.digest,
            metadata=self.metadata,
            release_url=f"https://github.com/Oxnight/botw-companion/releases/tag/v{self.VERSION}",
        )

    def installer(self, **values):
        return MacOSUpdateInstaller(
            data_root=self.root,
            application=self.executable,
            helper=self.helper,
            system=values.pop("system", "Darwin"),
            machine=values.pop("machine", "arm64"),
            frozen=values.pop("frozen", True),
            owner_uid=values.pop("owner_uid", 501),
            owner_gid=values.pop("owner_gid", 20),
            **values,
        )

    def test_coordinator_launches_a_detached_argument_list(self):
        calls = []

        def popen(command, **kwargs):
            calls.append((command, kwargs))
            return FakeProcess()

        state = self.installer(popen=popen).start(
            self.candidate(), parent_pid=4321, port=8765
        )
        self.assertEqual(state["status"], "scheduled")
        command, options = calls[0]
        self.assertEqual(command[0], "/bin/bash")
        self.assertIn("--bundle-version", command)
        self.assertIn("40.0.40", command)
        self.assertIn("--parent-pid", command)
        self.assertIn("4321", command)
        self.assertIn("--owner-uid", command)
        self.assertIn("501", command)
        self.assertIn("--owner-gid", command)
        self.assertIn("20", command)
        self.assertTrue(options["start_new_session"])
        self.assertTrue(options["close_fds"])
        self.assertFalse(options.get("shell", False))
        relay = Path(command[1])
        self.assertTrue(relay.is_file())
        # Windows only models the writable bit in chmod(), so it cannot
        # represent the POSIX 0700 mode used by the real macOS relay.
        if os.name == "posix":
            self.assertEqual(relay.stat().st_mode & 0o777, 0o700)
            self.assertEqual(
                (self.root / INSTALL_STATE_NAME).stat().st_mode & 0o777,
                0o600,
            )

    def test_only_a_frozen_apple_silicon_bundle_is_supported(self):
        self.assertTrue(self.installer().supported())
        self.assertFalse(self.installer(machine="x86_64").supported())
        self.assertFalse(self.installer(system="Windows").supported())
        self.assertFalse(self.installer(frozen=False).supported())

    def test_concurrent_requests_cannot_launch_two_macos_relays(self):
        entered, release = threading.Event(), threading.Event()
        calls, blocked = [], []

        def popen(*args, **kwargs):
            calls.append(True)
            entered.set()
            if not release.wait(3):
                raise OSError("test relay did not release")
            return FakeProcess()

        installer = self.installer(popen=popen)

        def start():
            try:
                installer.start(self.candidate(), parent_pid=1, port=8765)
            except MacOSUpdateError:
                blocked.append(True)

        first, second = threading.Thread(target=start), threading.Thread(target=start)
        first.start()
        try:
            self.assertTrue(entered.wait(3))
            second.start()
        finally:
            release.set()
            first.join(3)
            if second.ident is not None:
                second.join(3)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(calls, [True])
        self.assertEqual(blocked, [True])

    def test_metadata_must_be_the_verified_dmgs_adjacent_file(self):
        other = self.root / "other.metadata.json"
        other.write_bytes(self.metadata.read_bytes())
        with self.assertRaisesRegex(MacOSUpdateError, "sécurité"):
            self.installer().start(replace(self.candidate(), metadata=other), parent_pid=1, port=8765)

    def test_relay_exiting_before_handoff_does_not_schedule_shutdown(self):
        class ExitedProcess:
            def poll(self):
                return 2

        installer = self.installer(popen=lambda *args, **kwargs: ExitedProcess())
        with self.assertRaisesRegex(MacOSUpdateError, "démarrer"):
            installer.start(self.candidate(), parent_pid=1, port=8765)
        self.assertEqual(installer.status()["status"], "failed")
        self.assertTrue(installer.status()["can_retry"])

    def test_tampering_after_download_blocks_the_relay(self):
        self.dmg.write_bytes(b"tampered")
        with self.assertRaisesRegex(MacOSUpdateError, "sécurité"):
            self.installer().start(self.candidate(), parent_pid=1, port=8765)

    def test_candidate_metadata_must_still_be_ready_and_exact(self):
        self.metadata.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(MacOSUpdateError, "sécurité"):
            self.installer().start(self.candidate(), parent_pid=1, port=8765)

    def test_status_exposes_only_public_plist_fields(self):
        with (self.root / INSTALL_STATE_NAME).open("wb") as stream:
            plistlib.dump({
                "status": "failed",
                "version": self.VERSION,
                "message": "échec contrôlé",
                "can_retry": True,
                "secret": "never expose",
            }, stream)
        state = self.installer().status()
        self.assertEqual(state["status"], "failed")
        self.assertNotIn("secret", state)

    def test_interrupted_relay_recovers_status_and_live_relay_blocks_retry(self):
        installer = self.installer()
        backup = self.application.parent / '.BOTW Companion.app.backup-reference'
        backup.mkdir()
        for alive in (True, False):
            with self.subTest(alive=alive):
                with installer.state_path.open('wb') as stream:
                    plistlib.dump({'status': 'restarting', 'version': self.VERSION,
                                   'relay_pid': 1234, 'can_retry': False}, stream)
                with patch('botw_companion.macos_updates._relay_is_running', return_value=alive):
                    state = installer.status()
                    self.assertEqual(state['status'], 'restarting' if alive else 'failed')
                    self.assertEqual(state['can_retry'], not alive)
                    if alive:
                        with self.assertRaisesRegex(MacOSUpdateError, 'déjà en cours'):
                            installer.start(self.candidate(), parent_pid=1, port=8765)
                self.assertTrue(backup.is_dir())
                self.assertTrue(self.executable.is_file())
                self.assertTrue(self.dmg.is_file())
        from botw_companion.versioning import CURRENT_VERSION
        with installer.state_path.open('wb') as stream:
            plistlib.dump({'status': 'restarting', 'version': CURRENT_VERSION.display,
                           'relay_pid': 1234, 'can_retry': False}, stream)
        with patch('botw_companion.macos_updates._relay_is_running', return_value=False):
            self.assertEqual(installer.status()['status'], 'succeeded')
        self.assertTrue(backup.is_dir())

    def _atomic_swap_function(self):
        relay = (Path(__file__).resolve().parents[1] / 'botw_companion/macos_update_relay.sh').read_text(encoding='utf-8')
        start = relay.index('atomic_swap() {')
        # The JXA heredoc also contains closing braces. Stop after its delimiter
        # and the shell function's closing brace, before relay initialization.
        end_marker = '\nSWAP_JXA\n}'
        end = relay.index(end_marker, start) + len(end_marker)
        return relay[start:end]

    def test_detach_failure_diagnostic_is_translated_in_english(self):
        from botw_companion.english import translate_text
        self.assertEqual(translate_text('L’image disque macOS ne peut pas être démontée.'),
                         'The macOS disk image could not be detached.')

    @unittest.skipUnless(shutil.which('bash'), 'Requires Bash to parse the relay function')
    def test_atomic_swap_fixture_does_not_execute_relay_initialization(self):
        code = 'set -eu\n' + self._atomic_swap_function() + '\ndeclare -F atomic_swap\n'
        result = subprocess.run([shutil.which('bash'), '-c', code],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'atomic_swap')
        self.assertEqual(result.stderr, '')

    @unittest.skipUnless(sys.platform == 'darwin', 'Requires the native macOS atomic exchange API')
    def test_atomic_swap_preserves_both_bundles_and_can_be_reversed(self):
        left, right = self.base / 'Current $ (app).app', self.base / 'Backup Élimith.app'
        left.mkdir(); right.mkdir()
        (left / 'identity').write_text('old')
        (right / 'identity').write_text('new')
        code = self._atomic_swap_function() + '\natomic_swap "$1" "$2"\n'
        for expected in ('new', 'old'):
            result = subprocess.run(['/bin/bash', '-c', code, 'swap-test', str(left), str(right)],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((left / 'identity').read_text(), expected)
            self.assertEqual((right / 'identity').read_text(), 'old' if expected == 'new' else 'new')

    @unittest.skipUnless(sys.platform == 'darwin', 'Requires the native macOS atomic exchange API')
    def test_failed_atomic_swap_retains_the_application(self):
        result = subprocess.run(['/bin/bash', '-c', self._atomic_swap_function() + '\natomic_swap "$1" "$2"\n',
                                 'swap-test', str(self.application), str(self.base / 'missing.app')],
                                capture_output=True, text=True, timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Atomic bundle exchange failed; both bundles are retained.', result.stderr)
        self.assertFalse((self.base / 'missing.app').exists())
        self.assertEqual(self.executable.read_bytes(), b'arm64 app')

    def test_relay_script_contains_transactional_safety_checks(self):
        relay = (Path(__file__).resolve().parents[1] / "botw_companion" /
                 "macos_update_relay.sh").read_text(encoding="utf-8")
        for required in (
            "hdiutil verify", "-readonly", "-nobrowse", "codesign --verify --deep --strict",
            "CFBundleIdentifier", "CFBundleShortVersionString", "CFBundleVersion",
            "lipo -archs", "shasum -a 256", "/usr/bin/ditto", "administratorPrivileges",
            "rollback_performed", "Application.currentApplication", "launchctl asuser",
        ):
            self.assertIn(required, relay)
        self.assertNotIn("xattr -d", relay)
        self.assertNotIn("spctl --master-disable", relay)


if __name__ == "__main__":
    unittest.main()
