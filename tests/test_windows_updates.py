import argparse
import hashlib
from http.client import RemoteDisconnected
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

from botw_companion.windows_updates import (
    INSTALL_STATE_NAME,
    RELAY_LOG_PREPARATION_FAILED,
    UPDATER_EXE_NAME,
    WindowsInstallCandidate,
    WindowsUpdateError,
    WindowsUpdateInstaller,
    _probe_version,
    _external_process_environment,
    _wait_for_parent,
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
        self.digest = hashlib.sha256(self.installer.read_bytes()).hexdigest()
        self.metadata.write_text(json.dumps({
            "ready": True,
            "version": self.VERSION,
            "filename": self.installer.name,
            "size": self.installer.stat().st_size,
            "digest": f"sha256:{self.digest}",
        }), encoding="utf-8")
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

    def test_concurrent_install_requests_launch_only_one_relay(self):
        entered = threading.Event()
        release = threading.Event()
        launches = []
        results = []

        def popen(*args, **kwargs):
            launches.append(True)
            entered.set()
            if not release.wait(3):
                raise OSError("test relay did not release")
            return FakeProcess()

        coordinator = WindowsUpdateInstaller(
            data_root=self.root, application=self.application, helper=self.helper,
            system="Windows", frozen=True, popen=popen,
        )

        def install():
            try:
                results.append(coordinator.start(self.candidate(), parent_pid=1, port=8765))
            except WindowsUpdateError:
                results.append("blocked")

        first = threading.Thread(target=install)
        second = threading.Thread(target=install)
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
        self.assertEqual(len(launches), 1)
        self.assertIn("blocked", results)

    def test_portable_or_source_tree_never_offers_assisted_installation(self):
        self.uninstaller.unlink()
        coordinator = WindowsUpdateInstaller(
            data_root=self.root, application=self.application, helper=self.helper,
            system="Windows", frozen=True,
        )
        self.assertFalse(coordinator.supported())

    def test_windows_access_denied_is_not_treated_as_a_stopped_parent(self):
        import ctypes
        kernel = SimpleNamespace(OpenProcess=MagicMock(return_value=0),
                                 WaitForSingleObject=MagicMock(), CloseHandle=MagicMock())
        with patch.object(ctypes, "WinDLL", return_value=kernel, create=True), \
             patch.object(ctypes, "get_last_error", return_value=5, create=True), \
             patch("botw_companion.windows_updates.os.name", "nt"):
            self.assertFalse(_wait_for_parent(123))
        kernel.WaitForSingleObject.assert_not_called()

    def test_windows_relay_exiting_before_handoff_is_a_recoverable_error(self):
        installer = WindowsUpdateInstaller(
            data_root=self.root, application=self.application, helper=self.helper,
            system="Windows", frozen=True,
            popen=lambda *args, **kwargs: FakeProcess(returncode=2),
        )
        with self.assertRaisesRegex(WindowsUpdateError, "démarrer"):
            installer.start(self.candidate(), parent_pid=1, port=8765)
        self.assertEqual(installer.status()["status"], "failed")
        self.assertTrue(installer.status()["can_retry"])

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
        args = self.args()
        self.assertFalse(Path(args.log).parent.exists())

        def run(command, **kwargs):
            self.assertTrue(Path(args.log).parent.is_dir())
            setup_calls.append((command, kwargs))
            return SimpleNamespace(returncode=0)

        def popen(command, **kwargs):
            launch_calls.append((command, kwargs))
            return FakeProcess()

        with patch("botw_companion.windows_updates.platform.system", return_value="Windows"), \
             patch("botw_companion.windows_updates._wait_for_parent", return_value=True), \
             patch("botw_companion.windows_updates._probe_version", return_value=True), \
             patch("botw_companion.windows_updates._reset_windows_dll_search_path") as reset_dlls, \
             patch("botw_companion.windows_updates.subprocess.run", side_effect=run), \
             patch("botw_companion.windows_updates.subprocess.Popen", side_effect=popen):
            self.assertEqual(run_relay(args), 0)
        reset_dlls.assert_called_once_with()
        command, kwargs = setup_calls[0]
        self.assertIn("/NORESTART", command)
        self.assertIn("/NOFORCECLOSEAPPLICATIONS", command)
        self.assertIn("/ASSISTEDUPDATE=1", command)
        self.assertIn(f"/DIR={self.application.parent.resolve()}", command)
        log_arguments = [argument for argument in command if argument.startswith("/LOG=")]
        self.assertEqual(log_arguments, [f"/LOG={Path(args.log).resolve()}"])
        self.assertNotIn('"', log_arguments[0])
        self.assertNotIn("/SILENT", " ".join(command))
        self.assertFalse(kwargs["shell"])
        self.assertFalse(any(key.startswith("_PYI_") for key in kwargs["env"]))
        self.assertEqual(launch_calls[0][0], [str(self.application.resolve())])
        self.assertFalse(self.installer.exists())
        self.assertFalse(self.metadata.exists())
        state = json.loads((self.root / INSTALL_STATE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "succeeded")

    def test_silent_relay_restarts_server_directly_and_records_diagnostics(self):
        args = self.args()
        args.silent = True
        launches = []

        def popen(command, **kwargs):
            launches.append((command, kwargs))
            return FakeProcess()

        with patch("botw_companion.windows_updates.platform.system", return_value="Windows"), \
             patch("botw_companion.windows_updates._wait_for_parent", return_value=True), \
             patch("botw_companion.windows_updates._probe_version", return_value=True), \
             patch("botw_companion.windows_updates._reset_windows_dll_search_path"), \
             patch("botw_companion.windows_updates.subprocess.run",
                   return_value=SimpleNamespace(returncode=0)), \
             patch("botw_companion.windows_updates.subprocess.Popen", side_effect=popen):
            self.assertEqual(run_relay(args), 0)

        command, kwargs = launches[0]
        self.assertEqual(command, [
            str(self.application.resolve()), "--server", "--port", str(args.port),
        ])
        self.assertIs(kwargs["stderr"], __import__("subprocess").STDOUT)
        self.assertIn(
            "BOTW Companion restart diagnostics",
            Path(args.log).read_text(encoding="utf-8", errors="replace"),
        )

    def test_silent_restart_failure_is_reported_without_waiting_for_timeout(self):
        args = self.args()
        args.silent = True
        with patch("botw_companion.windows_updates.platform.system", return_value="Windows"), \
             patch("botw_companion.windows_updates._wait_for_parent", return_value=True), \
             patch("botw_companion.windows_updates._probe_version", return_value=False), \
             patch("botw_companion.windows_updates._reset_windows_dll_search_path"), \
             patch("botw_companion.windows_updates.subprocess.run",
                   return_value=SimpleNamespace(returncode=0)), \
             patch("botw_companion.windows_updates.subprocess.Popen",
                   return_value=FakeProcess(returncode=7)), \
             patch("botw_companion.windows_updates.time.sleep") as sleep:
            self.assertEqual(run_relay(args), 6)
        sleep.assert_not_called()
        state = json.loads((self.root / INSTALL_STATE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "failed")
        self.assertTrue(state["can_retry"])
        self.assertIn("code 7", state["message"])

    def test_relay_stops_before_setup_when_log_directory_cannot_be_created(self):
        args = self.args()
        with patch("botw_companion.windows_updates.platform.system", return_value="Windows"), \
             patch("botw_companion.windows_updates._wait_for_parent", return_value=True), \
             patch("botw_companion.windows_updates._prepare_installer_log",
                   side_effect=OSError("disk is read-only")), \
             patch("botw_companion.windows_updates._launch_updated_application") as reopen, \
             patch("botw_companion.windows_updates.subprocess.run") as setup:
            self.assertEqual(run_relay(args), RELAY_LOG_PREPARATION_FAILED)
        setup.assert_not_called()
        reopen.assert_called_once()
        state = json.loads((self.root / INSTALL_STATE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "failed")
        self.assertTrue(state["can_retry"])
        self.assertFalse(state["log_available"])

    def test_setup_failure_gets_a_fallback_log_when_inno_cannot_create_one(self):
        args = self.args()
        with patch("botw_companion.windows_updates.platform.system", return_value="Windows"), \
             patch("botw_companion.windows_updates._wait_for_parent", return_value=True), \
             patch("botw_companion.windows_updates._reset_windows_dll_search_path"), \
             patch("botw_companion.windows_updates.subprocess.run",
                   return_value=SimpleNamespace(returncode=1)), \
             patch("botw_companion.windows_updates.subprocess.Popen"):
            self.assertEqual(run_relay(args), 1)
        fallback = Path(args.log)
        self.assertTrue(fallback.is_file())
        self.assertIn("Process exit code: 1", fallback.read_text(encoding="utf-8"))
        state = json.loads((self.root / INSTALL_STATE_NAME).read_text(encoding="utf-8"))
        self.assertTrue(state["log_available"])

    def test_tampering_after_download_blocks_setup(self):
        args = self.args()
        self.installer.write_bytes(b"tampered setup")
        with patch("botw_companion.windows_updates.platform.system", return_value="Windows"), \
             patch("botw_companion.windows_updates._wait_for_parent", return_value=True), \
             patch("botw_companion.windows_updates._launch_updated_application") as reopen, \
             patch("botw_companion.windows_updates.subprocess.run") as setup:
            self.assertEqual(run_relay(args), 4)
        setup.assert_not_called()
        reopen.assert_called_once()
        self.assertTrue(self.installer.exists())
        state = json.loads((self.root / INSTALL_STATE_NAME).read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "failed")

    def test_tampered_metadata_blocks_coordinator_and_relay(self):
        self.metadata.write_text("{}", encoding="utf-8")
        coordinator = WindowsUpdateInstaller(
            data_root=self.root, application=self.application, helper=self.helper,
            system="Windows", frozen=True,
        )
        with self.assertRaisesRegex(WindowsUpdateError, "sécurité"):
            coordinator.start(self.candidate(), parent_pid=321, port=8765)
        with patch("botw_companion.windows_updates.platform.system", return_value="Windows"), \
             patch("botw_companion.windows_updates.subprocess.run") as setup:
            self.assertEqual(run_relay(self.args()), 2)
        setup.assert_not_called()

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

    def test_external_installer_environment_removes_pyinstaller_state_and_bundle_path(self):
        bundle = Path(self.temporary.name) / "bundle"
        nested = bundle / "runtime"
        external = Path(self.temporary.name) / "system"
        with patch.dict(os.environ, {
            "_PYI_APPLICATION_HOME_DIR": str(bundle),
            "_PYI_PARENT_PROCESS_LEVEL": "1",
            "PATH": os.pathsep.join((str(nested), str(external))),
        }, clear=True), patch.object(__import__("sys"), "_MEIPASS", str(bundle), create=True):
            environment = _external_process_environment()
        self.assertNotIn("_PYI_APPLICATION_HOME_DIR", environment)
        self.assertNotIn("_PYI_PARENT_PROCESS_LEVEL", environment)
        self.assertEqual(environment["PATH"], str(external))

    def test_relay_rejects_an_installer_outside_the_update_directory(self):
        outside = Path(self.temporary.name) / f"BOTW_Companion_{self.VERSION}_Setup.exe"
        outside.write_bytes(self.installer.read_bytes())
        args = self.args()
        args.installer = str(outside)
        with patch("botw_companion.windows_updates.platform.system", return_value="Windows"), \
             patch("botw_companion.windows_updates.subprocess.run") as setup:
            self.assertEqual(run_relay(args), 2)
        setup.assert_not_called()

    def test_transient_http_disconnect_during_restart_probe_is_retryable(self):
        opener = SimpleNamespace(open=lambda *args, **kwargs: (_ for _ in ()).throw(
            RemoteDisconnected("server is restarting")
        ))
        with patch("botw_companion.windows_updates.build_opener", return_value=opener):
            self.assertFalse(_probe_version(8765, self.VERSION))

    def test_unexpected_relay_failure_is_recorded_instead_of_crashing_silently(self):
        with patch("botw_companion.windows_updates.platform.system", return_value="Windows"), \
             patch("botw_companion.windows_updates._wait_for_parent", return_value=True), \
             patch("botw_companion.windows_updates.subprocess.run",
                   side_effect=RuntimeError("native launch failed")), \
             patch("botw_companion.windows_updates._launch_updated_application") as reopen:
            self.assertEqual(run_relay(self.args()), 1)
        reopen.assert_called_once()
        state = json.loads((self.root / INSTALL_STATE_NAME).read_text(encoding="utf-8"))
        diagnostic = Path(state["log_path"])
        self.assertEqual(state["status"], "failed")
        self.assertTrue(state["can_retry"])
        self.assertTrue(state["log_available"])
        self.assertIn("RuntimeError: native launch failed", diagnostic.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
