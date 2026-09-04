from pathlib import Path
import tempfile
import unittest

from botw_companion.macos_app import _server_arguments
from botw_companion.macos_launcher import (
    LauncherError,
    launch_server,
    load_config,
    server_command,
)


class FakeProcess:
    def poll(self):
        return None


class MacOSLauncherTests(unittest.TestCase):
    def test_load_config_accepts_utf8_and_rejects_non_object(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "launcher.json"
            path.write_text('{"port": 9000}', encoding="utf-8")
            self.assertEqual(load_config(path)["port"], 9000)
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(LauncherError):
                load_config(path)

    def test_frozen_server_reuses_the_packaged_executable(self):
        command = server_command(
            Path("/Applications/BOTW Companion.app/Contents/MacOS/BOTW Companion"),
            Path("/Applications/BOTW Companion.app/Contents/MacOS"),
            8765,
            {"save_path": "/tmp/save"},
            frozen=True,
        )
        self.assertEqual(command[1:3], ["--server", "--save-path"])
        self.assertIn("--arreter-avec-emulateur", command)

    def test_frozen_child_is_detached_logged_and_resets_pyinstaller(self):
        with tempfile.TemporaryDirectory() as temp:
            calls = []

            def popen(args, **kwargs):
                calls.append((args, kwargs))
                return FakeProcess()

            launch_server(
                Path("/tmp/BOTW Companion"),
                Path(temp),
                8765,
                {
                    "ryujinx_process_names": ["Ryujinx.Ava"],
                    "cemu_process_names": ["Cemu"],
                },
                Path(temp) / "launcher.log",
                popen=popen,
                frozen=True,
            )
            options = calls[0][1]
            self.assertTrue(options["start_new_session"])
            self.assertTrue(options["close_fds"])
            self.assertEqual(
                options["env"]["PYINSTALLER_RESET_ENVIRONMENT"], "1"
            )
            self.assertEqual(
                options["env"]["BOTW_RYUJINX_PROCESS_NAMES"], "Ryujinx.Ava"
            )

    def test_private_server_arguments_map_to_the_existing_cli(self):
        arguments = _server_arguments([
            "--server",
            "--save-path",
            "/tmp/save",
            "--port",
            "9876",
            "--sans-navigateur",
            "--arreter-avec-emulateur",
        ])
        self.assertEqual(arguments[0:2], ["interface", "/tmp/save"])
        self.assertIn("9876", arguments)
        self.assertIn("--sans-navigateur", arguments)
        self.assertIn("--arreter-avec-emulateur", arguments)


if __name__ == "__main__":
    unittest.main()
