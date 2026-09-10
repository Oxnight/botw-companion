import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from botw_companion.windows_updates import (
    INSTALL_STATE_NAME,
    UPDATER_EXE_NAME,
    WindowsInstallCandidate,
    WindowsUpdateError,
    WindowsUpdateInstaller,
    run_relay,
)


class FakeProcess:
    def __init__(self, returncode=None):
        self.returncode = returncode

    def poll(self):
        return self.returncode


class WindowsUpdateTests(unittest.TestCase):
    VERSION = "0.40.0-alpha." + "39"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "updates"
        self.root.mkdir(parents=True)
        self.application = Path(self.temporary.name) / "BOTW Companion.exe"
        self.uninstaller = Path(self.temporary.name) / "unins000.exe"
        self.helper = Path(self.temporary.name) / UPDATER_EXE_NAME
        self.application.write_bytes(b"application")
        self.uninstaller.write_bytes(b"uninstaller")
        self.helper.write_bytes(b"relay")
        self.installer = self.root / f"BOTW_Companion_{self.VERSION}_Setup.exe"
        self.installer.write_bytes(b"verified setup")
        self.metadata = self.root / f"{self.installer.name}.metadata.json"
        self.metadata.write_text("{}", encoding="utf-8")
        self.digest = hashlib.sha256(self.installer.read_bytes()).hexdigest()
        self.release_url = f"https://github.com/Oxnight/botw-companion/releases/tag/v{self.VERSION}"

    def tearDown(self):
        self.temporary.cleanup()

    def candidate(self):
        return WindowsInstallCandidate(
            version=self.VERSION,
            installer=self.installer,
            size=self.installer.stat().st_size,
            digest=self.digest,
            metadata=self.metadata,
            release_url=self.release_url,
        )

    def args(self):
        return argparse.Namespace(
            root=str(self.root), installer=str(self.installer), metadata=str(self.metadata),
            version=self.VERSION, digest=self.digest,
            size=self.installer.stat().st_size, parent_pid=123,
            application=str(self.application), port=8765,
            log=str(self.root / "logs" / "installation.log"),
            release_url=self.release_url,
            silent=False,
        )

    def test_coordinator_copies_relay_and_uses_argument_list(self):
        calls = []

        def popen(command, **kwargs):
            calls.append((command, kwargs))
            return FakeProcess()

        coordinator = WindowsUpdateInstaller(
            data_root=self.root, application=self.application, helper=self.helper,
            system="Windows", frozen=True, popen=popen,
        )
        state = coordinator.start(self.candidate(), parent_pid=321, port=8765)
        self.assertEqual(state["status"], "scheduled")
        self.assertEqual(len(calls), 1)
        command, kwargs = calls[0]
        self.assertIsInstance(command, list)
        self.assertTrue(Path(command[0]).is_file())
        self.assertIn("--parent-pid", command)
        self.assertIn("321", command)
        self.assertFalse(kwargs.get("shell", False))

    def test_portable_or_source_tree_never_offers_assisted_installation(self):
        self.uninstaller.unlink()
        coordinator = WindowsUpdateInstaller(
            data_root=self.root, application=self.application, helper=self.helper,
            system="Windows", frozen=True,
        )
        self.assertFalse(coordinator.supported())

    def test_relay_copy_failure_is_recoverable_and_never_starts_a_process(self):
        launches = []
        coordinator = WindowsUpdateInstaller(
            data_root=self.root, application=self.application, helper=self.helper,
            system="Windows", frozen=True,
            popen=lambda *args, **kwargs: launches.append((args, kwargs)),
        )
        with patch("botw_companion.windows_updates.shutil.copy2",
                   side_effect=OSError("disk full")):
            with self.assertRaises(WindowsUpdateError):
                coordinator.start(self.candidate(), parent_pid=321, port=8765)
        self.assertEqual(launches, [])
        state = json.loads((self.root / INSTALL_STATE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "failed")
        self.assertTrue(state["can_retry"])

    def test_relay_reverifies_then_installs_restarts_and_cleans_package(self):
        setup_calls = []
        launch_calls = []

        def run(command, **kwargs):
            setup_calls.append((command, kwargs))
            return SimpleNamespace(returncode=0)

        def popen(command, **kwargs):
            launch_calls.append((command, kwargs))
            return FakeProcess()

        with patch("botw_companion.windows_updates.platform.system", return_value="Windows"), \
             patch("botw_companion.windows_updates._wait_for_parent", return_value=True), \
             patch("botw_companion.windows_updates._probe_version", return_value=True), \
             patch("botw_companion.windows_updates.subprocess.run", side_effect=run), \
             patch("botw_companion.windows_updates.subprocess.Popen", side_effect=popen):
            self.assertEqual(run_relay(self.args()), 0)
        command, kwargs = setup_calls[0]
        self.assertIn("/NORESTART", command)
        self.assertIn("/NOFORCECLOSEAPPLICATIONS", command)
        self.assertIn("/ASSISTEDUPDATE=1", command)
        self.assertNotIn("/SILENT", " ".join(command))
        self.assertFalse(kwargs["shell"])
        self.assertEqual(launch_calls[0][0], [str(self.application.resolve())])
        self.assertFalse(self.installer.exists())
        self.assertFalse(self.metadata.exists())
        state = json.loads((self.root / INSTALL_STATE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "succeeded")

    def test_tampering_after_download_blocks_setup(self):
        args = self.args()
        self.installer.write_bytes(b"tampered setup")
        with patch("botw_companion.windows_updates.platform.system", return_value="Windows"), \
             patch("botw_companion.windows_updates._wait_for_parent", return_value=True), \
             patch("botw_companion.windows_updates.subprocess.run") as setup:
            self.assertEqual(run_relay(args), 4)
        setup.assert_not_called()
        self.assertTrue(self.installer.exists())
        state = json.loads((self.root / INSTALL_STATE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "failed")

    def test_cancelled_setup_keeps_verified_installer_and_reopens_app(self):
        with patch("botw_companion.windows_updates.platform.system", return_value="Windows"), \
             patch("botw_companion.windows_updates._wait_for_parent", return_value=True), \
             patch("botw_companion.windows_updates.subprocess.run",
                   return_value=SimpleNamespace(returncode=2)), \
             patch("botw_companion.windows_updates.subprocess.Popen") as launch:
            self.assertEqual(run_relay(self.args()), 2)
        self.assertTrue(self.installer.exists())
        self.assertTrue(self.metadata.exists())
        launch.assert_called_once()
        state = json.loads((self.root / INSTALL_STATE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "cancelled")
        self.assertTrue(state["can_retry"])

    def test_relay_rejects_an_installer_outside_the_update_directory(self):
        outside = Path(self.temporary.name) / f"BOTW_Companion_{self.VERSION}_Setup.exe"
        outside.write_bytes(self.installer.read_bytes())
        args = self.args()
        args.installer = str(outside)
        with patch("botw_companion.windows_updates.platform.system", return_value="Windows"), \
             patch("botw_companion.windows_updates.subprocess.run") as setup:
            self.assertEqual(run_relay(args), 2)
        setup.assert_not_called()


if __name__ == "__main__":
    unittest.main()
