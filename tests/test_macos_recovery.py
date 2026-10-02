"""Execute the production rollback and exit handlers with controlled processes.

Native DMG, signature, and packaged-server checks remain in the macOS CI job.
These tests verify filesystem ordering and recovery without macOS utilities.
"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.name == "posix" and shutil.which("bash"), "POSIX shell recovery tests")
class MacOSRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.application = self.root / "BOTW Companion.app"
        self.backup = self.root / "backup.app"
        self.application.mkdir()
        self.backup.mkdir()
        (self.application / "identity").write_text("new")
        (self.backup / "identity").write_text("old")
        self.script = (Path(__file__).resolve().parents[1] / "botw_companion" /
                       "macos_update_relay.sh").read_text()

    def tearDown(self):
        self.temporary.cleanup()

    def function(self, name):
        start = self.script.index(f"{name}() {{")
        end = self.script.index("\n}\n", start) + 3
        return self.script[start:end]

    def run_shell(self, body):
        return subprocess.run([shutil.which("bash"), "-c", body], cwd=self.root,
                              capture_output=True, text=True, timeout=5)

    def test_new_process_is_stopped_before_the_bundle_is_removed(self):
        result = self.run_shell('''
set -euo pipefail
APPLICATION="$PWD/BOTW Companion.app"
BACKUP="$PWD/backup.app"
RUNTIME_VERSION="expected"
TEST_MODE=1
stop_new_application() { test "$(cat "$APPLICATION/identity")" = new; echo stopped >> order; }
launch_application() { test "$(cat "$APPLICATION/identity")" = old; echo launched >> order; }
wait_for_version() { echo ready >> order; }
''' + self.function("restore_backup") + "\nrestore_backup\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "order").read_text().splitlines(), ["stopped", "launched", "ready"])
        self.assertEqual((self.application / "identity").read_text(), "old")
        self.assertFalse(self.backup.exists())

    def test_unconfirmed_process_preserves_both_the_new_bundle_and_backup(self):
        result = self.run_shell('''
set -euo pipefail
APPLICATION="$PWD/BOTW Companion.app"
BACKUP="$PWD/backup.app"
TEST_MODE=1
stop_new_application() { return 1; }
launch_application() { exit 99; }
''' + self.function("restore_backup") + "\nif restore_backup; then exit 98; fi\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.application / "identity").read_text(), "new")
        self.assertEqual((self.backup / "identity").read_text(), "old")

    def test_unexpected_exit_before_replacement_reopens_the_current_application(self):
        result = self.run_shell('''
PARENT_STOPPED=1
RECOVERY_HANDLED=0
COMMITTED=0
TEST_MODE=0
BACKUP="$PWD/missing-backup"
STATE="$PWD/state"
launch_application() { echo reopened > recovery; }
write_state() { echo "$1" > state-result; }
cleanup() { echo cleaned > cleanup-result; }
''' + self.function("finish_relay") + "\ntrap finish_relay EXIT\nexit 12\n")
        self.assertEqual(result.returncode, 12)
        self.assertEqual((self.root / "recovery").read_text().strip(), "reopened")
        self.assertTrue((self.root / "cleanup-result").is_file())
