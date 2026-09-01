import unittest
from pathlib import Path


class WindowsDsuBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]

    def test_cmake_selects_winsock_and_pinned_shared_sdl(self):
        text = (self.root / "third_party" / "JoyConDSU" / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("platform_socket_windows.c", text)
        self.assertIn("platform_runtime_windows.c", text)
        self.assertIn("target_link_libraries(JoyConDSU PRIVATE Ws2_32)", text)
        self.assertIn("SDL3-3.4.14.tar.gz", text)
        self.assertIn(
            "30d4aa2b3037718142b32dffd4e72f917ebb6cc5227150e7bb9c45efb2153aeb",
            text,
        )
        self.assertIn("$<TARGET_FILE:SDL3::SDL3-shared>", text)

    def test_windows_socket_adapter_uses_native_winsock_lifecycle(self):
        source = (
            self.root
            / "third_party"
            / "JoyConDSU"
            / "Sources"
            / "JoyConDSU"
            / "platform_socket_windows.c"
        ).read_text(encoding="utf-8")
        for symbol in (
            "WSAStartup",
            "WSACleanup",
            "ioctlsocket",
            "closesocket",
            "WSAGetLastError",
            "WSAEWOULDBLOCK",
        ):
            self.assertIn(symbol, source)

    def test_windows_build_script_emits_self_contained_runtime(self):
        script = (self.root / "tools" / "build_joycon_dsu_windows.ps1").read_text(encoding="utf-8")
        for filename in ("JoyConDSU.exe", "SDL3.dll", "manifest.json", "SDL3-LICENSE.txt"):
            self.assertIn(filename, script)
        self.assertIn("Get-FileHash -Algorithm SHA256", script)
        self.assertIn("-NoNewline", script)
        self.assertIn('botw_companion\\dsu\\windows', script)

    def test_windows_engine_exposes_a_cooperative_named_stop_event(self):
        source = (
            self.root
            / "third_party"
            / "JoyConDSU"
            / "Sources"
            / "JoyConDSU"
            / "platform_runtime_windows.c"
        ).read_text(encoding="utf-8")
        self.assertIn("CreateEventW", source)
        self.assertIn("WaitForSingleObject", source)
        self.assertIn("BOTWCompanion.JoyConDSU.Stop", source)
        self.assertIn("dsu_platform_cleanup", source)

    def test_local_windows_build_includes_native_engine_in_full_application(self):
        script = (self.root / "tools" / "build_windows_app.ps1").read_text(encoding="utf-8")
        self.assertIn("build_joycon_dsu_windows.ps1", script)
        self.assertIn("JoyConDSU.exe", script)
        self.assertIn("SDL3.dll", script)
        self.assertIn("BOTW Companion.spec", script)

    def test_sdl_hidapi_and_pairing_are_forced_before_initialization(self):
        source = (
            self.root
            / "third_party"
            / "JoyConDSU"
            / "Sources"
            / "JoyConDSU"
            / "main.c"
        ).read_text(encoding="utf-8")
        hidapi = source.index("SDL_HINT_JOYSTICK_HIDAPI_JOY_CONS")
        combine = source.index("SDL_HINT_JOYSTICK_HIDAPI_COMBINE_JOY_CONS")
        initialize = source.index("SDL_Init(SDL_INIT_GAMEPAD")
        self.assertLess(hidapi, initialize)
        self.assertLess(combine, initialize)

    def test_native_engine_emits_machine_readable_quality_telemetry(self):
        source = (
            self.root
            / "third_party"
            / "JoyConDSU"
            / "Sources"
            / "JoyConDSU"
            / "main.c"
        ).read_text(encoding="utf-8")
        self.assertIn("BOTW_DSU_TELEMETRY", source)
        for field in (
            "received_hz=", "sent_hz=", "sample_age_ms=",
            "received_jitter_mean_ms=", "duplicate_timestamps=",
            "send_errors=", "disconnects=", "calibration_valid=",
        ):
            self.assertIn(field, source)
