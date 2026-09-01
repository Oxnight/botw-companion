import plistlib
import struct
import unittest
from pathlib import Path


class MacOSBundleTests(unittest.TestCase):
    def test_custom_icon_is_declared_and_contains_retina_sizes(self):
        root = Path(__file__).resolve().parents[1]
        contents = root / "macos" / "BOTW Companion.app" / "Contents"
        plist = plistlib.loads((contents / "Info.plist").read_bytes())
        self.assertEqual(plist["CFBundleIconFile"], "AppIcon.icns")
        self.assertEqual(plist["CFBundleVersion"], "45")
        self.assertEqual(plist["CFBundleShortVersionString"], "0.40.0")

        icon = contents / "Resources" / plist["CFBundleIconFile"]
        data = icon.read_bytes()
        self.assertEqual(data[:4], b"icns")
        self.assertEqual(struct.unpack(">I", data[4:8])[0], len(data))
        for representation in (b"icp4", b"icp5", b"icp6", b"ic07", b"ic08",
                               b"ic09", b"ic10", b"ic11", b"ic12", b"ic13", b"ic14"):
            self.assertIn(representation, data)
        self.assertGreater(len(data), 1_000_000)

        master = root / "macos" / "AppIcon-1024.png"
        self.assertTrue(master.is_file())
        self.assertGreater(master.stat().st_size, 500_000)

    def test_joycon_dsu_runtime_is_packaged_and_executable(self):
        root = Path(__file__).resolve().parents[1]
        runtime = root / "botw_companion" / "dsu" / "JoyConDSU"
        launcher = root / "botw_companion" / "dsu" / "launch_managed.sh"
        self.assertTrue(runtime.is_file())
        self.assertTrue(launcher.is_file())
        self.assertTrue(runtime.stat().st_mode & 0o111)
        self.assertTrue(launcher.stat().st_mode & 0o111)
        self.assertGreater(runtime.stat().st_size, 30_000)

    def test_native_source_uses_timestamped_sensor_events(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "third_party" / "JoyConDSU" / "Sources" / "JoyConDSU" / "main.c").read_text()
        self.assertIn("SDL_EVENT_GAMEPAD_SENSOR_UPDATE", source)
        self.assertIn("event->sensor_timestamp", source)
        self.assertIn("SENSOR_STALL_NS", source)
        self.assertIn("MotionDsuTimeline", source)
        self.assertIn("MAX_REQUESTS_PER_TURN = 64", source)
        self.assertIn("dsu_motion_values_finite", source)
        self.assertNotIn("SDL_GetGamepadSensorData(", source)
        self.assertNotIn("SDL_DelayNS(250000ULL)", source)
        self.assertIn("SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_JOYCON_LEFT", source)
        self.assertIn("SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_JOYCON_RIGHT", source)

    def test_supervisor_builds_the_current_native_sources(self):
        root = Path(__file__).resolve().parents[1]
        launcher = (root / "botw_companion" / "dsu" / "launch_managed.sh").read_text()
        self.assertIn("main.c", launcher)
        self.assertIn("dsu_protocol.c", launcher)
        self.assertIn("motion_pipeline.c", launcher)
        self.assertIn("calibration.c", launcher)
        self.assertIn("dsu_clients.c", launcher)
        self.assertIn("telemetry.c", launcher)
        self.assertIn("source_hash", launcher)

    def test_telemetry_cannot_disconnect_a_fresh_calibrated_controller(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "third_party" / "JoyConDSU" / "Sources" / "JoyConDSU" / "main.c").read_text()
        available = source.split("static bool controller_available", 1)[1].split(
            "static bool telemetry_health_ok", 1
        )[0]
        self.assertNotIn("motion_pipeline_received_hz", available)
        self.assertIn("controller_available(&controller", source)

    def test_launcher_restarts_an_outdated_server(self):
        root = Path(__file__).resolve().parents[1]
        launcher = root / "macos" / "BOTW Companion.app" / "Contents" / "MacOS" / "BOTW Companion"
        text = launcher.read_text()
        self.assertIn('EXPECTED_VERSION="0.40.0a23"', text)
        self.assertIn('"${URL}api/version"', text)
        self.assertIn('"${URL}api/shutdown"', text)


if __name__ == "__main__":
    unittest.main()
