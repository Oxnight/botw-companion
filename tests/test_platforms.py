import unittest
from pathlib import Path

from botw_companion.platforms import (
    cemu_is_running,
    cemu_save_roots,
    companion_data_dir,
    platform_metadata,
    ryujinx_is_running,
    ryujinx_save_roots,
    server_instance_guard,
)
from botw_companion.platforms.windows import (
    WindowsConsoleShutdownHandler,
    WindowsNamedMutex,
)


class PlatformTests(unittest.TestCase):
    def test_macos_paths_remain_unchanged(self):
        home = Path("/Users/link")
        self.assertEqual(
            companion_data_dir(system="Darwin", environ={}, home=home),
            home / "Library/Application Support/BOTW Companion",
        )
        self.assertEqual(
            ryujinx_save_roots(system="Darwin", environ={}, home=home, which=lambda _name: None),
            [
                home / "Library/Application Support/Ryujinx/bis/user/save",
                home / ".config/Ryujinx/bis/user/save",
            ],
        )

    def test_windows_uses_native_appdata_locations(self):
        environ = {
            "APPDATA": "C:/Users/Link/AppData/Roaming",
            "LOCALAPPDATA": "C:/Users/Link/AppData/Local",
        }
        home = Path("C:/Users/Link")
        self.assertEqual(
            companion_data_dir(system="Windows", environ=environ, home=home),
            Path("C:/Users/Link/AppData/Local/BOTW Companion"),
        )
        roots = ryujinx_save_roots(
            system="Windows", environ=environ, home=home, which=lambda _name: None,
        )
        self.assertEqual(
            roots[0],
            Path("C:/Users/Link/AppData/Roaming/Ryujinx/bis/user/save"),
        )

    def test_windows_paths_preserve_spaces_accents_and_non_ascii_characters(self):
        environ = {
            "APPDATA": "C:/Utilisateurs/Épona 漢字/AppData/Roaming",
            "LOCALAPPDATA": "C:/Utilisateurs/Épona 漢字/AppData/Local",
        }
        home = Path("C:/Utilisateurs/Épona 漢字")
        self.assertEqual(
            companion_data_dir(system="Windows", environ=environ, home=home),
            Path("C:/Utilisateurs/Épona 漢字/AppData/Local/BOTW Companion"),
        )
        self.assertEqual(
            ryujinx_save_roots(
                system="Windows", environ=environ, home=home, which=lambda _name: None,
            )[0],
            Path("C:/Utilisateurs/Épona 漢字/AppData/Roaming/Ryujinx/bis/user/save"),
        )

    def test_windows_fallback_paths_work_without_appdata_variables(self):
        home = Path("C:/Users/Link")
        self.assertEqual(
            companion_data_dir(system="Windows", environ={}, home=home),
            home / "AppData/Local/BOTW Companion",
        )
        self.assertEqual(
            ryujinx_save_roots(
                system="Windows", environ={}, home=home, which=lambda _name: None,
            )[0],
            home / "AppData/Roaming/Ryujinx/bis/user/save",
        )

    def test_windows_detects_an_explicit_portable_installation(self):
        environ = {
            "APPDATA": "C:/Users/Link/AppData/Roaming",
            "RYUJINX_EXECUTABLE": "D:/Games/Ryujinx/Ryujinx.exe",
        }
        roots = ryujinx_save_roots(
            system="Windows",
            environ=environ,
            home=Path("C:/Users/Link"),
            which=lambda _name: None,
        )
        self.assertIn(
            Path("D:/Games/Ryujinx/portable/bis/user/save"),
            roots,
        )

    def test_windows_detects_a_ryujinx_executable_on_path(self):
        def which(name: str) -> str | None:
            return f"E:/Portable/Ryujinx/{name}" if name == "Ryujinx.exe" else None

        roots = ryujinx_save_roots(
            system="Windows",
            environ={"APPDATA": "C:/Users/Link/AppData/Roaming"},
            home=Path("C:/Users/Link"),
            which=which,
        )
        self.assertIn(
            Path("E:/Portable/Ryujinx/portable/bis/user/save"),
            roots,
        )

    def test_explicit_overrides_have_priority_on_every_platform(self):
        environ = {
            "BOTW_COMPANION_DATA_DIR": "D:/BOTW/Data",
            "RYUJINX_DATA_DIR": "E:/RyujinxData",
            "APPDATA": "C:/Users/Link/AppData/Roaming",
        }
        self.assertEqual(
            companion_data_dir(system="Windows", environ=environ),
            Path("D:/BOTW/Data"),
        )
        roots = ryujinx_save_roots(
            system="Windows", environ=environ, which=lambda _name: None,
        )
        self.assertEqual(roots[0], Path("E:/RyujinxData/bis/user/save"))

    def test_platform_metadata_is_ready_for_the_web_interface(self):
        windows = platform_metadata(
            "Windows",
            environ={"LOCALAPPDATA": "C:/Users/Link/AppData/Local"},
            home=Path("C:/Users/Link"),
        )
        self.assertEqual(windows["id"], "windows")
        self.assertEqual(windows["label"], "Windows")
        self.assertEqual(windows["native_dsu_engine"], "JoyConDSU.exe")
        self.assertEqual(windows["shortcut_modifier"], "Ctrl")
        self.assertIn("raccourci Windows", windows["relaunch_hint"])
        self.assertEqual(
            Path(windows["data_directory"]),
            Path("C:/Users/Link/AppData/Local/BOTW Companion"),
        )
        self.assertEqual(
            Path(windows["dsu_log_path"]),
            Path("C:/Users/Link/AppData/Local/BOTW Companion/joycon-dsu.log"),
        )

        macos = platform_metadata(
            "Darwin",
            environ={},
            home=Path("/Users/link"),
        )
        self.assertEqual(macos["label"], "macOS")
        self.assertEqual(macos["native_dsu_engine"], "JoyConDSU")
        self.assertEqual(macos["shortcut_modifier"], "⌘")
        self.assertIn("Dock", macos["relaunch_hint"])
        self.assertEqual(
            macos["dsu_log_path"],
            "/Users/link/Library/Application Support/BOTW Companion/joycon-dsu.log",
        )

    def test_windows_process_detection_accepts_both_ryujinx_names(self):
        self.assertTrue(ryujinx_is_running(
            system="Windows",
            process_names=lambda: {"explorer.exe", "RYUJINX.AVA.EXE"},
        ))
        self.assertFalse(ryujinx_is_running(
            system="Windows",
            process_names=lambda: {"explorer.exe", "python.exe"},
        ))

    def test_windows_process_detection_accepts_configured_extra_names(self):
        self.assertTrue(ryujinx_is_running(
            system="Windows",
            process_names=lambda: {"Custom-Ryujinx.exe"},
            environ={"BOTW_RYUJINX_PROCESS_NAMES": "Other.exe;Custom-Ryujinx.exe"},
        ))


    def test_macos_cemu_default_and_custom_mlc_paths(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            data = home / "Library/Application Support/Cemu"
            data.mkdir(parents=True)
            custom = home / "Games/CemuMLC"
            (data / "settings.xml").write_text(
                f"<content><mlc_path>{custom}</mlc_path></content>", encoding="utf-8"
            )
            roots = cemu_save_roots(system="Darwin", environ={}, home=home, which=lambda _name: None)
            self.assertIn(custom / "usr/save", roots)
            self.assertIn(data / "mlc01/usr/save", roots)

    def test_windows_cemu_default_and_explicit_paths(self):
        roots = cemu_save_roots(
            system="Windows",
            environ={
                "APPDATA": "C:/Users/Link/AppData/Roaming",
                "LOCALAPPDATA": "C:/Users/Link/AppData/Local",
                "CEMU_MLC_PATH": "D:/CemuMLC",
                "CEMU_EXECUTABLE": "E:/Portable/Cemu/Cemu.exe",
            },
            home=Path("C:/Users/Link"), which=lambda _name: None,
        )
        self.assertIn(Path("D:/CemuMLC/usr/save"), roots)
        self.assertIn(Path("C:/Users/Link/AppData/Roaming/Cemu/mlc01/usr/save"), roots)
        self.assertIn(Path("E:/Portable/Cemu/mlc01/usr/save"), roots)

    def test_cemu_process_detection_on_windows_and_macos(self):
        self.assertTrue(cemu_is_running(
            system="Windows", process_names=lambda: {"explorer.exe", "CEMU.EXE"},
        ))
        self.assertTrue(cemu_is_running(
            system="Darwin", process_names=lambda: {"Finder", "Cemu"}, environ={},
        ))
        self.assertFalse(cemu_is_running(
            system="Darwin", process_names=lambda: {"Finder"}, environ={},
        ))

    def test_windows_server_mutex_is_local_and_user_specific(self):
        names = []

        class FakeGuard:
            def __init__(self, name):
                names.append(name)

        first = server_instance_guard(
            system="Windows",
            environ={"LOCALAPPDATA": "C:/Users/Link/AppData/Local"},
            mutex_factory=FakeGuard,
        )
        second = server_instance_guard(
            system="Windows",
            environ={"LOCALAPPDATA": "C:/Users/Zelda/AppData/Local"},
            mutex_factory=FakeGuard,
        )
        self.assertIsInstance(first, FakeGuard)
        self.assertIsInstance(second, FakeGuard)
        self.assertTrue(names[0].startswith("Local\\BOTWCompanion.Server."))
        self.assertNotEqual(names[0], names[1])

    def test_windows_named_mutex_rejects_a_second_instance_and_closes_its_handle(self):
        class FakeKernel32:
            def __init__(self):
                self.closed = []

            def CreateMutexW(self, _security, _owner, _name):
                return 123

            def CloseHandle(self, handle):
                self.closed.append(handle)
                return True

        kernel32 = FakeKernel32()
        mutex = WindowsNamedMutex(
            "Local\\BOTWCompanion.Server.test",
            kernel32=kernel32,
            get_last_error=lambda: 183,
        )
        self.assertFalse(mutex.acquire())
        self.assertEqual(kernel32.closed, [123])

    def test_windows_named_mutex_is_released_after_a_normal_session(self):
        class FakeKernel32:
            def __init__(self):
                self.closed = []

            def CreateMutexW(self, _security, _owner, _name):
                return 456

            def CloseHandle(self, handle):
                self.closed.append(handle)
                return True

        kernel32 = FakeKernel32()
        mutex = WindowsNamedMutex(
            "Local\\BOTWCompanion.Server.test",
            kernel32=kernel32,
            get_last_error=lambda: 0,
        )
        self.assertTrue(mutex.acquire())
        self.assertTrue(mutex.acquire())
        mutex.close()
        self.assertEqual(kernel32.closed, [456])

    def test_windows_console_events_request_a_clean_shutdown(self):
        class FakeKernel32:
            def __init__(self):
                self.calls = []

            def SetConsoleCtrlHandler(self, callback, enabled):
                self.calls.append((callback, enabled))
                return True

        reasons = []
        kernel32 = FakeKernel32()
        handler = WindowsConsoleShutdownHandler(reasons.append, kernel32=kernel32)
        native_callback = kernel32.calls[0][0]
        self.assertTrue(native_callback(5))
        self.assertEqual(reasons, ["windows_control_5"])
        handler.close()
        self.assertFalse(kernel32.calls[-1][1])


if __name__ == "__main__":
    unittest.main()
