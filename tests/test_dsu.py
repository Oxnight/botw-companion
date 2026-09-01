import tempfile
import unittest
from pathlib import Path

from botw_companion.dsu.manager import (
    DsuManager,
    WINDOWS_CREATE_NO_WINDOW,
    _windows_runtime_directory,
)
from botw_companion.dsu.windows_runtime import signal_stop_event, stop_event_name


class FakeProcess:
    def __init__(self, _args, **_kwargs):
        self.pid = 4242
        self.returncode = None
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


class DsuManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.executable = root / "JoyConDSU"
        self.launcher = root / "launch_managed.sh"
        self.sdl = root / "libSDL3.0.dylib"
        for path in (self.executable, self.launcher, self.sdl):
            path.write_bytes(b"test")
        self.processes = []

    def tearDown(self):
        self.temp.cleanup()

    def manager(self, probe=lambda: None):
        def popen(*args, **kwargs):
            process = FakeProcess(*args, **kwargs)
            self.processes.append(process)
            return process
        return DsuManager(
            executable=self.executable,
            launcher=self.launcher,
            sdl_library=self.sdl,
            system="Darwin",
            machine="arm64",
            support_dir=Path(self.temp.name) / "support",
            probe=probe,
            popen=popen,
        )

    def test_dsu_is_off_by_default(self):
        status = self.manager().status()
        self.assertEqual(status["schema_version"], 3)
        self.assertEqual(status["state"], "off")
        self.assertFalse(status["running"])
        self.assertFalse(status["enabled_by_default"])
        self.assertEqual(status["platform"], "macOS")
        self.assertEqual(status["engine_name"], "JoyConDSU")
        self.assertTrue(status["log_path"].endswith("joycon-dsu.log"))
        self.assertEqual(status["diagnostic"]["status"], "inactive")
        self.assertIsNone(status["telemetry"])

    def test_structured_telemetry_is_parsed_without_locale_ambiguity(self):
        parsed = DsuManager._parse_telemetry_line(
            "BOTW_DSU_TELEMETRY\tversion=1\thealth=ok\tuptime_s=10.0\t"
            "clients=1\treceived_hz=199.750\tsent_hz=200.125\t"
            "calibration_valid=1"
        )
        self.assertEqual(parsed["health"], "ok")
        self.assertEqual(parsed["clients"], 1)
        self.assertAlmostEqual(parsed["received_hz"], 199.75)
        self.assertIsNone(DsuManager._parse_telemetry_line("journal ordinaire"))
        self.assertIsNone(DsuManager._parse_telemetry_line(
            "BOTW_DSU_TELEMETRY\tversion=1\thealth=ok\treceived_hz=nan"
        ))

    def test_signal_quality_uses_calibration_rate_jitter_age_and_errors(self):
        telemetry = {
            "health": "ok",
            "calibration_valid": 1,
            "measurement_age_seconds": 1.0,
            "received_hz": 200.0,
            "sent_hz": 199.8,
            "clients": 1,
            "sample_age_ms": 3.0,
            "received_jitter_mean_ms": 0.3,
            "received_jitter_max_ms": 3.0,
            "sent_jitter_mean_ms": 0.4,
            "sent_jitter_max_ms": 4.0,
            "sensor_events": 10_000,
            "sent_packets": 10_000,
            "duplicate_timestamps": 0,
            "regressive_timestamps": 0,
            "invalid_values": 0,
            "nonfinite_samples": 0,
            "send_errors": 0,
        }
        self.assertEqual(
            DsuManager._diagnostic("ready", True, telemetry)["status"],
            "excellent",
        )
        telemetry.update(received_hz=150.0, received_jitter_mean_ms=2.0)
        self.assertEqual(
            DsuManager._diagnostic("ready", True, telemetry)["status"],
            "correct",
        )
        telemetry["received_hz"] = 80.0
        self.assertEqual(
            DsuManager._diagnostic("ready", True, telemetry)["status"],
            "unstable",
        )
        telemetry["calibration_valid"] = 0
        self.assertEqual(
            DsuManager._diagnostic("ready", True, telemetry)["status"],
            "recalibration",
        )

    def test_windows_reports_a_missing_native_engine_without_blocking_the_site(self):
        manager = DsuManager(
            system="Windows",
            support_dir=Path(self.temp.name) / "windows-support",
            probe=lambda: None,
        )
        status = manager.status()
        self.assertEqual(status["state"], "unavailable")
        self.assertEqual(status["platform"], "Windows")
        self.assertEqual(status["engine_name"], "JoyConDSU.exe")
        self.assertIn("JoyConDSU.exe", status["message"])

    def test_windows_finds_the_clone_runtime_after_a_native_build(self):
        root = Path(self.temp.name)
        resource = root / "package-dsu"
        runtime = root / "project" / "windows" / "native-dsu"
        resource.mkdir()
        runtime.mkdir(parents=True)
        (runtime / "JoyConDSU.exe").write_bytes(b"MZ")
        (runtime / "SDL3.dll").write_bytes(b"MZ")
        self.assertEqual(
            _windows_runtime_directory(resource, environ={}, project_root=root / "project"),
            runtime,
        )

    def test_windows_launches_the_native_engine_hidden_and_directly(self):
        root = Path(self.temp.name)
        runtime = root / "native-dsu"
        runtime.mkdir()
        executable = runtime / "JoyConDSU.exe"
        library = runtime / "SDL3.dll"
        executable.write_bytes(b"MZ")
        library.write_bytes(b"MZ")
        calls = []

        def popen(args, **kwargs):
            calls.append((args, kwargs))
            process = FakeProcess(args, **kwargs)
            self.processes.append(process)
            return process

        manager = DsuManager(
            system="Windows",
            runtime_dir=runtime,
            support_dir=root / "support",
            probe=lambda: None,
            popen=popen,
            windows_stop_signal=lambda _pid: False,
        )
        status = manager.start()
        self.assertEqual(status["state"], "starting")
        self.assertEqual(calls[0][0], [str(executable)])
        self.assertEqual(calls[0][1]["cwd"], runtime)
        self.assertEqual(
            calls[0][1]["creationflags"],
            WINDOWS_CREATE_NO_WINDOW,
        )
        manager.stop()

    def test_windows_stop_uses_the_named_event_before_termination(self):
        root = Path(self.temp.name)
        runtime = root / "native-dsu"
        runtime.mkdir()
        (runtime / "JoyConDSU.exe").write_bytes(b"MZ")
        (runtime / "SDL3.dll").write_bytes(b"MZ")
        signaled = []

        def stop_signal(pid):
            signaled.append(pid)
            self.processes[0].returncode = 0
            return True

        manager = DsuManager(
            system="Windows",
            runtime_dir=runtime,
            support_dir=root / "support",
            probe=lambda: None,
            popen=lambda *args, **kwargs: self.processes.append(
                FakeProcess(*args, **kwargs)
            ) or self.processes[-1],
            windows_stop_signal=stop_signal,
        )
        manager.start()
        manager.stop()
        self.assertEqual(signaled, [4242])
        self.assertFalse(self.processes[0].terminated)

    def test_windows_named_stop_event_is_opened_signaled_and_closed(self):
        class FakeKernel32:
            def __init__(self):
                self.opened = []
                self.signaled = []
                self.closed = []

            def OpenEventW(self, access, inherited, name):
                self.opened.append((access, inherited, name))
                return 91

            def SetEvent(self, handle):
                self.signaled.append(handle)
                return True

            def CloseHandle(self, handle):
                self.closed.append(handle)
                return True

        kernel32 = FakeKernel32()
        self.assertTrue(signal_stop_event(4242, kernel32=kernel32))
        self.assertEqual(kernel32.opened[0][2], stop_event_name(4242))
        self.assertEqual(kernel32.signaled, [91])
        self.assertEqual(kernel32.closed, [91])

    def test_process_architecture_never_blocks_dsu_before_real_launch(self):
        manager = DsuManager(
            executable=self.executable,
            launcher=self.launcher,
            sdl_library=self.sdl,
            system="Darwin",
            machine="x86_64",
            support_dir=Path(self.temp.name) / "support-rosetta",
            probe=lambda: None,
            popen=lambda *args, **kwargs: FakeProcess(*args, **kwargs),
        )
        self.assertEqual(manager.status()["state"], "off")

    def test_supervisor_explicitly_launches_the_arm64_binary(self):
        launcher = Path(__file__).resolve().parents[1] / "botw_companion" / "dsu" / "launch_managed.sh"
        text = launcher.read_text()
        self.assertIn('/usr/bin/arch -arm64 "$RUNTIME"', text)
        self.assertIn("motion_pipeline.c", text)
        self.assertIn("/usr/bin/xcrun --sdk macosx --find clang", text)
        self.assertIn("/usr/bin/xcrun --sdk macosx --show-sdk-path", text)
        self.assertIn('-isysroot "$sdk_path"', text)
        self.assertIn('SDKROOT="$sdk_path"', text)
        self.assertIn('RUNTIME="$BINARY"', text)
        self.assertIn("JoyConDSU-$source_hash", text)
        self.assertNotIn('wait "$child_pid"\nchild_pid=""', text)

    def test_start_waits_for_controller_and_stop_terminates_process(self):
        manager = self.manager()
        started = manager.start()
        self.assertEqual(started["state"], "starting")
        self.assertTrue(started["running"])
        stopped = manager.stop()
        self.assertEqual(stopped["state"], "off")
        self.assertTrue(self.processes[0].terminated)

    def test_real_protocol_probe_marks_controller_ready(self):
        manager = self.manager(lambda: {"connected": True, "motion": True})
        # Première sonde = vérification du port avant lancement; la simulation
        # d'un serveur déjà présent doit empêcher une seconde instance.
        result = manager.start()
        self.assertEqual(result["state"], "error")
        self.assertIn("déjà utilisé", result["message"])
        self.assertFalse(self.processes)

    def test_running_server_reports_ready_after_protocol_confirmation(self):
        answers = iter([None, {"connected": True, "motion": True}])

        def probe():
            return next(answers, {"connected": True, "motion": True})

        manager = self.manager(probe)
        result = manager.start()
        self.assertEqual(result["state"], "ready")
        self.assertTrue(result["controller_connected"])
        manager.close()

    def test_close_always_stops_the_owned_process(self):
        manager = self.manager()
        manager.start()
        manager.close()
        self.assertTrue(self.processes[0].terminated)

    def test_clear_error_returns_to_off_state(self):
        manager = self.manager()
        manager._last_error = "ancienne erreur"
        manager.stop()
        self.assertEqual(manager.status()["state"], "off")

    def test_inventory_exposes_all_controllers_and_motion_capabilities(self):
        output = (
            "BOTW_DSU_CONTROLLERS\t1\n"
            "CONTROLLER\t1\t1406\t8201\t14\t1\t1\tjoyconpair\t"
            "Nintendo Switch Joy-Con Pair\thid://pair\n"
            "CONTROLLER\t2\t1118\t654\t2\t0\t0\txbox360\t"
            "Xbox 360 Controller\tXInput#0\n"
        )

        class Result:
            returncode = 0
            stdout = output
            stderr = ""

        manager = DsuManager(
            executable=self.executable,
            launcher=self.launcher,
            sdl_library=self.sdl,
            system="Darwin",
            support_dir=Path(self.temp.name) / "support-inventory",
            probe=lambda: None,
            run=lambda *args, **kwargs: Result(),
            popen=lambda *args, **kwargs: FakeProcess(*args, **kwargs),
        )
        controllers = manager.controllers(force=True)
        self.assertEqual(len(controllers), 2)
        self.assertTrue(controllers[0]["compatible"])
        self.assertEqual(controllers[0]["kind"], "joycon_pair")
        self.assertFalse(controllers[1]["compatible"])
        self.assertEqual(controllers[1]["name"], "Xbox 360 Controller")

    def test_selected_controller_path_is_forwarded_to_native_engine(self):
        root = Path(self.temp.name)
        runtime = root / "native-dsu-selected"
        runtime.mkdir()
        executable = runtime / "JoyConDSU.exe"
        library = runtime / "SDL3.dll"
        executable.write_bytes(b"MZ")
        library.write_bytes(b"MZ")
        inventory = (
            "BOTW_DSU_CONTROLLERS\t1\n"
            "CONTROLLER\t7\t1356\t3302\t4\t1\t1\tps5\t"
            "DualSense Wireless Controller\thid://dualsense\n"
        )

        class Result:
            returncode = 0
            stdout = inventory
            stderr = ""

        calls = []

        def popen(args, **kwargs):
            calls.append((args, kwargs))
            process = FakeProcess(args, **kwargs)
            self.processes.append(process)
            return process

        manager = DsuManager(
            system="Windows",
            runtime_dir=runtime,
            support_dir=root / "support-selected",
            probe=lambda: None,
            run=lambda *args, **kwargs: Result(),
            popen=popen,
            windows_stop_signal=lambda _pid: False,
        )
        source = manager.controllers(force=True)[0]
        manager.start(source["id"])
        self.assertEqual(
            calls[0][0],
            [str(executable), "--controller-path", "hid://dualsense"],
        )
        self.assertEqual(manager.status()["selected_source"]["name"],
                         "DualSense Wireless Controller")
        manager.stop()



if __name__ == "__main__":
    unittest.main()