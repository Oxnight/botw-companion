import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from botw_companion import windows_launcher
from botw_companion import windows_app


class FakeProcess:
    def poll(self):
        return None


class WindowsLauncherTests(unittest.TestCase):
    def test_load_config_accepts_utf8_bom_and_rejects_non_object(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "launcher.json"
            path.write_text('\ufeff{"port": 8765}', encoding="utf-8")
            self.assertEqual(windows_launcher.load_config(path)["port"], 8765)
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(windows_launcher.LauncherError):
                windows_launcher.load_config(path)

    def test_project_and_python_discovery_prioritize_the_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / "pyproject.toml").write_text("[project]", encoding="utf-8")
            (project / "botw_companion").mkdir()
            runtime = project / "runtime" / "pythonw.exe"
            runtime.parent.mkdir()
            runtime.write_bytes(b"MZ")
            venv = project / ".venv" / "Scripts" / "pythonw.exe"
            venv.parent.mkdir(parents=True)
            venv.write_bytes(b"MZ")
            self.assertEqual(
                windows_launcher.find_project_root(str(project), {}),
                project.resolve(),
            )
            self.assertEqual(
                windows_launcher.find_python(project, {}),
                runtime.resolve(),
            )

    def test_focus_existing_window_uses_its_title(self):
        class FakeUser32:
            def __init__(self):
                self.foreground = []

            def EnumWindows(self, callback, _lparam):
                callback(12, 0)
                callback(34, 0)

            def IsWindowVisible(self, _hwnd):
                return True

            def GetWindowTextLengthW(self, hwnd):
                return len("Autre fenêtre" if hwnd == 12 else "BOTW Companion")

            def GetWindowTextW(self, hwnd, buffer, _length):
                buffer.value = "Autre fenêtre" if hwnd == 12 else "BOTW Companion"

            def ShowWindow(self, hwnd, _mode):
                self.foreground.append(("restore", hwnd))

            def SetForegroundWindow(self, hwnd):
                self.foreground.append(("foreground", hwnd))
                return True

        api = FakeUser32()
        self.assertTrue(windows_launcher.focus_companion_window(user32=api))
        self.assertEqual(api.foreground[-1], ("foreground", 34))

    def test_existing_server_is_reused_without_a_second_browser_when_focused(self):
        opened = []
        with tempfile.TemporaryDirectory() as temp, patch.object(
            windows_launcher,
            "companion_data_dir",
            return_value=Path(temp),
        ):
            result = windows_launcher.run(
                probe=lambda _port, timeout: {
                    "application": "BOTW Companion",
                    "version": windows_launcher.__version__,
                },
                focus=lambda: True,
                browser=lambda url: opened.append(url),
            )
        self.assertEqual(result, 0)
        self.assertEqual(opened, [])

    def test_existing_server_opens_the_page_when_windows_cannot_focus_it(self):
        opened = []
        with tempfile.TemporaryDirectory() as temp, patch.object(
            windows_launcher,
            "companion_data_dir",
            return_value=Path(temp),
        ):
            windows_launcher.run(
                probe=lambda _port, timeout: {
                    "application": "BOTW Companion",
                    "version": windows_launcher.__version__,
                },
                focus=lambda: False,
                browser=lambda url: opened.append(url),
            )
        self.assertEqual(opened, ["http://127.0.0.1:8765"])

    def test_new_server_is_hidden_monitored_and_opens_once(self):
        opened = []
        launched = []
        probe_results = iter([None, {
            "application": "BOTW Companion",
            "version": windows_launcher.__version__,
        }])

        def probe(_port, timeout):
            return next(probe_results)

        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "project"
            project.mkdir()
            python = project / "runtime" / "pythonw.exe"
            data = Path(temp) / "data"
            with patch.object(windows_launcher, "companion_data_dir", return_value=data), \
                    patch.object(windows_launcher, "port_available", return_value=True), \
                    patch.object(windows_launcher, "find_project_root", return_value=project), \
                    patch.object(windows_launcher, "find_python", return_value=python), \
                    patch.object(windows_launcher, "launch_server", side_effect=lambda *args, **kwargs: launched.append((args, kwargs)) or FakeProcess()):
                windows_launcher.run(
                    probe=probe,
                    browser=lambda url: opened.append(url),
                )
        self.assertEqual(len(launched), 1)
        self.assertEqual(opened, ["http://127.0.0.1:8765"])

    def test_server_command_enables_ryujinx_monitoring_without_browser(self):
        command = windows_launcher.server_command(
            Path("C:/BOTW/runtime/pythonw.exe"),
            Path("C:/BOTW"),
            8765,
            {},
        )
        self.assertIn("--sans-navigateur", command)
        self.assertIn("--arreter-avec-ryujinx", command)
        self.assertEqual(command[-2:], ["--sans-navigateur", "--arreter-avec-ryujinx"])

    def test_frozen_server_command_reuses_the_installed_executable(self):
        command = windows_launcher.server_command(
            Path("C:/Programs/BOTW Companion/BOTW Companion.exe"),
            Path("C:/Programs/BOTW Companion"),
            9876,
            {"save_path": "D:/Ryujinx/save"},
            frozen=True,
        )
        self.assertEqual(
            Path(command[0]),
            Path("C:/Programs/BOTW Companion/BOTW Companion.exe"),
        )
        self.assertEqual(command[1], "--server")
        self.assertIn("--save-path", command)
        self.assertIn("D:/Ryujinx/save", command)
        self.assertIn("--arreter-avec-ryujinx", command)

    def test_windows_app_translates_private_server_arguments(self):
        self.assertEqual(
            windows_app._server_arguments([
                "--server",
                "--port",
                "9876",
                "--save-path",
                "D:/Ryujinx/save",
            ]),
            [
                "interface",
                "D:/Ryujinx/save",
                "--port",
                "9876",
                "--sans-navigateur",
                "--arreter-avec-ryujinx",
            ],
        )

    def test_package_self_test_supports_a_windowed_runtime_without_stdio(self):
        with patch.object(windows_app, "packaged_resource_errors", return_value=[]), \
                patch.object(windows_app.sys, "stdout", None), \
                patch.object(windows_app.sys, "stderr", None):
            self.assertEqual(windows_app.package_self_test(), 0)

    def test_launch_server_uses_no_console_and_passes_extra_process_names(self):
        calls = []
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            python = root / "pythonw.exe"
            python.write_bytes(b"MZ")

            def fake_popen(command, **kwargs):
                calls.append((command, kwargs))
                return FakeProcess()

            windows_launcher.launch_server(
                python,
                root,
                8765,
                {"ryujinx_process_names": ["Ryujinx.exe", "Custom.exe"]},
                root / "launcher.log",
                popen=fake_popen,
            )
        _command, options = calls[0]
        self.assertTrue(options["creationflags"] & windows_launcher.CREATE_NO_WINDOW)
        self.assertEqual(
            options["env"]["BOTW_RYUJINX_PROCESS_NAMES"],
            "Ryujinx.exe;Custom.exe",
        )

    def test_frozen_launch_stays_hidden_and_uses_the_same_executable(self):
        calls = []
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            executable = root / "BOTW Companion.exe"
            executable.write_bytes(b"MZ")

            windows_launcher.launch_server(
                executable,
                root,
                8765,
                {},
                root / "launcher.log",
                popen=lambda command, **kwargs: calls.append(
                    (command, kwargs)
                ) or FakeProcess(),
                frozen=True,
            )
        command, options = calls[0]
        self.assertEqual(command[:2], [str(executable), "--server"])
        self.assertTrue(options["creationflags"] & windows_launcher.CREATE_NO_WINDOW)
        self.assertEqual(options["env"]["PYINSTALLER_RESET_ENVIRONMENT"], "1")

    def test_windows_installer_and_shortcut_assets_are_complete(self):
        root = Path(__file__).resolve().parents[1]
        windows = root / "windows"
        vbs = (windows / "BOTW Companion.vbs").read_text(encoding="utf-8")
        installer = (windows / "Installer BOTW Companion.ps1").read_text(encoding="utf-8")
        self.assertIn("pythonw.exe", vbs)
        self.assertIn("shell.Run(command, 0, True)", vbs)
        self.assertNotIn("cmd.exe", vbs.casefold())
        self.assertIn("wscript.exe", installer.casefold())
        self.assertIn("BOTW Companion.lnk", installer)
        self.assertIn("project-root.txt", installer)
        icon = (windows / "BOTW Companion.ico").read_bytes()
        reserved, kind, count = struct.unpack_from("<HHH", icon)
        self.assertEqual((reserved, kind), (0, 1))
        self.assertGreaterEqual(count, 8)

    def test_installer_default_configuration_is_valid_json_shape(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "windows" / "Installer BOTW Companion.ps1").read_text(encoding="utf-8")
        self.assertIn("schema_version = 1", text)
        self.assertIn('port = 8765', text)
        self.assertIn('"Ryujinx.Ava.exe"', text)


if __name__ == "__main__":
    unittest.main()
