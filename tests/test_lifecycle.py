import socket
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.request import Request, urlopen

from botw_companion.lifecycle import (
    RyujinxLifecycleWatcher,
    WebLifecycle,
    probe_companion_server,
)
from botw_companion.server import serve


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class WebLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.lifecycle = WebLifecycle(120, self.clock)

    def test_startup_without_browser_does_not_stop_automatically(self):
        self.assertFalse(self.lifecycle.has_browser)
        self.clock.advance(24 * 60 * 60)
        self.assertFalse(self.lifecycle.should_shutdown())

    def test_heartbeat_is_diagnostic_and_does_not_create_a_deadline(self):
        self.clock.advance(100)
        response = self.lifecycle.heartbeat()
        self.assertEqual(response, {"active": True, "inactivity_seconds": 120.0})
        self.assertTrue(self.lifecycle.has_browser)
        self.clock.advance(24 * 60 * 60)
        self.assertFalse(self.lifecycle.should_shutdown())

    def test_manual_shutdown_is_immediate(self):
        self.lifecycle.request_shutdown()
        self.assertTrue(self.lifecycle.should_shutdown())

    def test_minimum_inactivity_value_is_kept_for_api_compatibility(self):
        lifecycle = WebLifecycle(1, self.clock)
        self.assertEqual(lifecycle.inactivity_seconds, 60.0)
        self.clock.advance(24 * 60 * 60)
        self.assertFalse(lifecycle.should_shutdown())

    def test_shutdown_reason_is_recorded(self):
        self.lifecycle.request_shutdown("ryujinx_ferme")
        self.assertTrue(self.lifecycle.should_shutdown())
        self.assertEqual(self.lifecycle.shutdown_reason, "ryujinx_ferme")


class FakeResponse:
    def __init__(self, payload: bytes, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        pass

    def read(self) -> bytes:
        return self.payload


class ServerProbeTests(unittest.TestCase):
    def test_probe_accepts_only_a_real_companion_server(self):
        calls = []

        def opener(url, timeout):
            calls.append((url, timeout))
            return FakeResponse(b'{"application":"BOTW Companion","version":"0.40.0a23"}')

        result = probe_companion_server(9876, timeout=0.25, opener=opener)
        self.assertEqual(result["version"], "0.40.0a23")
        self.assertEqual(calls, [("http://127.0.0.1:9876/api/version", 0.25)])

    def test_probe_rejects_an_unrelated_service_on_the_same_port(self):
        result = probe_companion_server(
            opener=lambda _url, timeout: FakeResponse(b'{"application":"autre","version":"1"}'),
        )
        self.assertIsNone(result)


class RyujinxLifecycleWatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.running = {"value": False}
        self.reasons = []
        self.watcher = RyujinxLifecycleWatcher(
            lambda: self.running["value"],
            self.reasons.append,
            poll_seconds=10,
            close_grace_seconds=20,
            resume_gap_seconds=40,
            clock=self.clock,
        )

    def test_never_stops_before_ryujinx_has_really_been_seen(self):
        for _index in range(20):
            self.assertFalse(self.watcher.check_once())
            self.clock.advance(10)
        self.assertEqual(self.reasons, [])
        self.assertEqual(self.watcher.status()["state"], "attente_ryujinx")

    def test_confirmed_ryujinx_exit_requests_shutdown(self):
        self.running["value"] = True
        self.watcher.check_once()
        self.running["value"] = False
        self.clock.advance(10)
        self.assertFalse(self.watcher.check_once())
        self.clock.advance(19)
        self.assertFalse(self.watcher.check_once())
        self.clock.advance(1)
        self.assertTrue(self.watcher.check_once())
        self.assertEqual(self.reasons, ["ryujinx_ferme"])

    def test_wake_from_sleep_never_looks_like_a_confirmed_exit(self):
        self.running["value"] = True
        self.watcher.check_once()
        self.running["value"] = False
        self.clock.advance(120)
        self.assertFalse(self.watcher.check_once())
        self.assertEqual(self.watcher.status()["state"], "reprise_apres_veille")
        self.assertEqual(self.reasons, [])

    def test_detection_error_is_not_treated_as_a_closed_game(self):
        errors = RyujinxLifecycleWatcher(
            lambda: (_ for _ in ()).throw(PermissionError("accès refusé")),
            self.reasons.append,
            clock=self.clock,
        )
        self.assertFalse(errors.check_once())
        self.assertEqual(errors.status()["state"], "erreur_detection")
        self.assertEqual(self.reasons, [])


class FakeInstanceGuard:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.closed = False

    def acquire(self) -> bool:
        return self.available

    def close(self) -> None:
        self.closed = True


class FakeDsuManager:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.closed = False

    def status(self) -> dict:
        return {"state": "off"}

    def start(self) -> dict:
        self.started = True
        return self.status()

    def stop(self) -> dict:
        self.stopped = True
        return self.status()

    def close(self) -> None:
        self.closed = True


class ServerLifecycleIntegrationTests(unittest.TestCase):
    @staticmethod
    def free_port() -> int:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            return listener.getsockname()[1]

    def test_version_probe_shutdown_and_cleanup_form_one_lifecycle(self):
        port = self.free_port()
        guard = FakeInstanceGuard()
        dsu = FakeDsuManager()
        thread = threading.Thread(
            target=serve,
            args=(lambda: {},),
            kwargs={
                "port": port,
                "open_browser": False,
                "instance_guard": guard,
                "dsu_manager": dsu,
            },
        )
        thread.start()
        identity = None
        for _attempt in range(50):
            identity = probe_companion_server(port, timeout=0.1)
            if identity is not None:
                break
            time.sleep(0.02)
        self.assertIsNotNone(identity)
        self.assertEqual(identity["application"], "BOTW Companion")
        with urlopen(Request(
            f"http://127.0.0.1:{port}/api/shutdown",
            data=b"",
            method="POST",
        ), timeout=1) as response:
            self.assertEqual(response.status, 200)
        thread.join(timeout=3)
        self.assertFalse(thread.is_alive())
        self.assertTrue(dsu.stopped)
        self.assertTrue(dsu.closed)
        self.assertTrue(guard.closed)

    def test_existing_dsu_api_controls_the_platform_manager(self):
        port = self.free_port()
        dsu = FakeDsuManager()
        thread = threading.Thread(
            target=serve,
            args=(lambda: {},),
            kwargs={
                "port": port,
                "open_browser": False,
                "instance_guard": FakeInstanceGuard(),
                "dsu_manager": dsu,
            },
        )
        thread.start()
        for _attempt in range(50):
            if probe_companion_server(port, timeout=0.1) is not None:
                break
            time.sleep(0.02)
        with urlopen(Request(
            f"http://127.0.0.1:{port}/api/dsu/start",
            data=b"",
            method="POST",
        ), timeout=1) as response:
            self.assertEqual(response.status, 200)
        self.assertTrue(dsu.started)
        with urlopen(Request(
            f"http://127.0.0.1:{port}/api/dsu/stop",
            data=b"",
            method="POST",
        ), timeout=1) as response:
            self.assertEqual(response.status, 200)
        self.assertTrue(dsu.stopped)
        with urlopen(Request(
            f"http://127.0.0.1:{port}/api/shutdown",
            data=b"",
            method="POST",
        ), timeout=1):
            pass
        thread.join(timeout=3)
        self.assertFalse(thread.is_alive())

    def test_selected_save_caption_is_served_as_a_private_jpeg(self):
        with tempfile.TemporaryDirectory() as directory:
            slot = Path(directory) / "1"
            slot.mkdir()
            content = b"\xff\xd8\xff\xe0" + b"slot preview".ljust(124, b"\0") + b"\xff\xd9"
            (slot / "caption.jpg").write_bytes(content)
            port = self.free_port()
            thread = threading.Thread(
                target=serve,
                args=(lambda: {"sauvegarde": {"chemin": str(slot)}},),
                kwargs={
                    "port": port,
                    "open_browser": False,
                    "instance_guard": FakeInstanceGuard(),
                    "dsu_manager": FakeDsuManager(),
                },
            )
            thread.start()
            for _attempt in range(50):
                if probe_companion_server(port, timeout=0.1) is not None:
                    break
                time.sleep(0.02)
            try:
                with urlopen(f"http://127.0.0.1:{port}/api/save-caption", timeout=1) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers["Content-Type"], "image/jpeg")
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                    self.assertEqual(response.read(), content)
            finally:
                with urlopen(Request(
                    f"http://127.0.0.1:{port}/api/shutdown",
                    data=b"",
                    method="POST",
                ), timeout=1):
                    pass
                thread.join(timeout=3)
            self.assertFalse(thread.is_alive())

    def test_second_server_is_rejected_before_binding_a_port(self):
        guard = FakeInstanceGuard(False)
        with self.assertRaisesRegex(OSError, "fonctionne déjà"):
            serve(
                lambda: {},
                port=self.free_port(),
                open_browser=False,
                instance_guard=guard,
                dsu_manager=FakeDsuManager(),
            )


if __name__ == "__main__":
    unittest.main()
