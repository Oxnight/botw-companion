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

    def test_new_process_is_stopped_before_atomic_rollback_and_old_health_is_required(self):
        result = self.run_shell('''
set -euo pipefail
APPLICATION="$PWD/BOTW Companion.app"
BACKUP="$PWD/backup.app"
RUNTIME_VERSION="expected"
ORIGINAL_RUNTIME_VERSION="old-runtime"
TEST_MODE=1
stop_new_application() { test "$(cat "$APPLICATION/identity")" = new; echo stopped >> order; }
atomic_swap() {
  test "$1" = "$APPLICATION" && test "$2" = "$BACKUP"
  echo swapped >> order
  mv "$APPLICATION" "$PWD/swap-temporary"
  mv "$BACKUP" "$APPLICATION"
  mv "$PWD/swap-temporary" "$BACKUP"
}
launch_application() { test "$(cat "$APPLICATION/identity")" = old; echo launched >> order; }
wait_for_version() { test "$1" = old-runtime; echo ready >> order; }
''' + self.function("restore_backup") + "\nrestore_backup\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "order").read_text().splitlines(), ["stopped", "swapped", "launched", "ready"])
        self.assertEqual((self.application / "identity").read_text(), "old")
        self.assertFalse(self.backup.exists())

    def test_normal_gui_rollback_does_not_claim_success_without_a_ready_old_server(self):
        result = self.run_shell('''
set -euo pipefail
APPLICATION="$PWD/BOTW Companion.app"
BACKUP="$PWD/backup.app"
ORIGINAL_RUNTIME_VERSION="old-runtime"
TEST_MODE=0
stop_new_application() { return 0; }
atomic_swap() {
  mv "$APPLICATION" "$PWD/swap-temporary"
  mv "$BACKUP" "$APPLICATION"
  mv "$PWD/swap-temporary" "$BACKUP"
}
launch_application() { return 0; }
wait_for_version() { test "$1" = old-runtime; return 1; }
''' + self.function("restore_backup") + "\nif restore_backup; then exit 99; fi\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.application / "identity").read_text(), "old")
        self.assertEqual((self.backup / "identity").read_text(), "new")

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
SWAPPED=0
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

    def detach_function(self):
        return self.function('detach_image').replace('/usr/bin/hdiutil', 'fake_hdiutil').replace('/bin/sleep', 'fake_sleep')

    def test_owned_mount_is_detached_without_parsing_display_paths(self):
        self.assertNotIn('/sbin/mount', self.function('detach_image'))
        result = self.run_shell('''
set -euo pipefail
IMAGE_ATTACHED=1
MOUNT_POINT="$PWD/alias mount"
mkdir "$MOUNT_POINT"
fake_sleep() { :; }
fake_hdiutil() { test "$1" = detach; test "$2" = "$MOUNT_POINT"; echo detached >> calls; }
''' + self.detach_function() + '''
detach_image
test "$IMAGE_ATTACHED" = 0
test ! -d "$MOUNT_POINT"
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'calls').read_text().splitlines(), ['detached'])

    def test_busy_owned_mount_has_bounded_retry_and_force_fallback(self):
        result = self.run_shell('''
set -euo pipefail
IMAGE_ATTACHED=1
MOUNT_POINT="$PWD/owned mount"
mkdir "$MOUNT_POINT"
fake_sleep() { echo sleep >> pauses; }
fake_hdiutil() {
  test "$1" = detach; test "$2" = "$MOUNT_POINT"
  echo "$#" >> calls
  test "$#" = 3 && test "$3" = -force
}
''' + self.detach_function() + '''
detach_image
test "$IMAGE_ATTACHED" = 0
test ! -d "$MOUNT_POINT"
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'calls').read_text().splitlines(), ['2', '2', '2', '3'])
        self.assertEqual(len((self.root / 'pauses').read_text().splitlines()), 2)

    def test_failed_detach_preserves_ownership_and_both_bundles(self):
        result = self.run_shell('''
set -euo pipefail
IMAGE_ATTACHED=1
MOUNT_POINT="$PWD/owned mount"
mkdir "$MOUNT_POINT"
fake_sleep() { :; }
fake_hdiutil() { echo attempt >> calls; return 1; }
''' + self.detach_function() + '''
if detach_image; then exit 99; fi
test "$IMAGE_ATTACHED" = 1
test -d "$MOUNT_POINT"
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len((self.root / 'calls').read_text().splitlines()), 4)
        self.assertEqual((self.application / 'identity').read_text(), 'new')
        self.assertEqual((self.backup / 'identity').read_text(), 'old')

    def test_unowned_mount_is_not_forcibly_detached(self):
        result = self.run_shell('''
set -euo pipefail
IMAGE_ATTACHED=0
MOUNT_POINT="$PWD/not-owned"
fake_sleep() { exit 98; }
fake_hdiutil() { exit 99; }
''' + self.detach_function() + '\ndetach_image\n')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_source_image_is_released_before_atomic_publication_and_kill(self):
        start = self.script.index('validate_application "$STAGING"')
        detach = self.script.index('\ndetach_image || {', start)
        swap = self.script.index('if ! atomic_swap "$APPLICATION" "$BACKUP"', detach)
        kill = self.script.index('BOTW_UPDATE_KILL_AFTER_SWAP', swap)
        self.assertLess(start, detach)
        self.assertLess(detach, swap)
        self.assertLess(swap, kill)

    def test_installation_helper_keeps_failed_mount_for_cleanup(self):
        script = (Path(__file__).resolve().parents[1] / 'tools/test_macos_installation.sh').read_text()
        start = script.index('detach_dmg() {')
        end = script.index('\n}\n', start) + 3
        function = script[start:end].replace('/usr/bin/hdiutil', 'fake_hdiutil').replace('/bin/sleep', 'fake_sleep')
        result = self.run_shell('''
set -euo pipefail
MOUNT_POINT="$PWD/test mount"
fake_sleep() { :; }
fake_hdiutil() { echo attempt >> calls; return 1; }
''' + function + '''
if detach_dmg; then exit 99; fi
test "$MOUNT_POINT" = "$PWD/test mount"
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len((self.root / 'calls').read_text().splitlines()), 4)
