from contextlib import contextmanager
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request

from botw_companion.lifecycle import open_loopback
from botw_companion.manual_tracking import ManualTrackingStore
from botw_companion.preferences import PreferenceStore
from botw_companion.route_sessions import RouteSessionStore
from botw_companion.server import CONTENT_SECURITY_POLICY, SESSION_HEADER, serve
from botw_companion.macos_launcher import request_shutdown as macos_shutdown
from botw_companion.windows_launcher import request_shutdown as windows_shutdown


class FakeGuard:
    def acquire(self) -> bool:
        return True

    def close(self) -> None:
        pass


class FakeNotifier:
    def close(self) -> None:
        pass


class FakeDsuManager:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def status(self) -> dict:
        return {"state": "off"}

    def start(self, _source_id=None) -> dict:
        self.started = True
        return {"state": "off"}

    def stop(self) -> dict:
        self.stopped = True
        return {"state": "off"}

    def close(self) -> None:
        pass


class ServerSecurityTests(unittest.TestCase):
    TOKEN = "security-integration-token"

    @contextmanager
    def running_server(self, *, token: str | None = TOKEN):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ready = threading.Event()
            ports: list[int] = []
            dsu = FakeDsuManager()

            def report_ready(port: int) -> None:
                ports.append(port)
                ready.set()

            kwargs = {
                "port": 0,
                "open_browser": False,
                "tracking_store": ManualTrackingStore(root / "manual.json"),
                "route_store": RouteSessionStore(root / "routes.json"),
                "preference_store": PreferenceStore(root / "preferences.json"),
                "dsu_manager": dsu,
                "running_emulators_provider": lambda: [],
                "instance_guard": FakeGuard(),
                "shutdown_notifier_factory": lambda _callback: FakeNotifier(),
                "server_ready": report_ready,
            }
            if token is not None:
                kwargs["session_token"] = token
            thread = threading.Thread(
                target=serve,
                args=(lambda: {},),
                kwargs=kwargs,
                daemon=True,
            )
            thread.start()
            self.assertTrue(ready.wait(5))
            try:
                yield thread, ports[0], dsu
            finally:
                if thread.is_alive():
                    identity = self.get_json(ports[0], "/api/version")[1]
                    self.request(
                        ports[0],
                        "POST",
                        "/api/shutdown",
                        headers={SESSION_HEADER: identity["session_token"]},
                    )
                thread.join(timeout=3)
                self.assertFalse(thread.is_alive())

    @staticmethod
    def request(port: int, method: str, path: str, *, body: object = None,
                headers: dict[str, str] | None = None):
        request_headers = dict(headers or {})
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            request_headers.setdefault("Content-Type", "application/json")
        request = Request(
            f"http://127.0.0.1:{port}{path}",
            data=data if data is not None else (b"" if method in {"POST", "PUT"} else None),
            headers=request_headers,
            method=method,
        )
        try:
            with open_loopback(request, timeout=2) as response:
                return response.status, response.read(), response.headers
        except HTTPError as exc:
            return exc.code, exc.read(), exc.headers

    @classmethod
    def get_json(cls, port: int, path: str):
        status, body, headers = cls.request(port, "GET", path)
        return status, json.loads(body), headers

    def test_version_index_and_every_response_receive_security_material(self):
        with self.running_server() as (_thread, port, _dsu):
            status, identity, headers = self.get_json(port, "/api/version")
            self.assertEqual(status, 200)
            self.assertEqual(identity["session_token"], self.TOKEN)
            self.assertEqual(headers["Content-Security-Policy"], CONTENT_SECURITY_POLICY)
            self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
            self.assertEqual(headers["X-Frame-Options"], "DENY")
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
            self.assertEqual(headers["Referrer-Policy"], "no-referrer")
            self.assertEqual(headers["Cross-Origin-Resource-Policy"], "same-origin")

            status, body, index_headers = self.request(port, "GET", "/")
            text = body.decode()
            self.assertEqual(status, 200)
            self.assertEqual(index_headers["Cache-Control"], "no-store")
            self.assertIn(f'content="{self.TOKEN}"', text)
            self.assertNotIn("__BOTW_SESSION_TOKEN__", text)

    def test_host_origin_fetch_metadata_and_cors_preflight_are_rejected(self):
        with self.running_server() as (thread, port, _dsu):
            status, _body, _headers = self.request(
                port, "POST", "/api/shutdown",
                headers={SESSION_HEADER: self.TOKEN, "Origin": "https://evil.example"},
            )
            self.assertEqual(status, 403)
            status, _body, _headers = self.request(
                port, "POST", "/api/shutdown",
                headers={SESSION_HEADER: self.TOKEN, "Sec-Fetch-Site": "cross-site"},
            )
            self.assertEqual(status, 403)
            status, _body, headers = self.request(
                port, "OPTIONS", "/api/preferences",
                headers={"Origin": "https://evil.example"},
            )
            self.assertEqual(status, 403)
            self.assertIsNone(headers.get("Access-Control-Allow-Origin"))

            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            connection.putrequest("GET", "/api/version", skip_host=True)
            connection.putheader("Host", "evil.example")
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, 421)
            response.read()
            connection.close()
            self.assertTrue(thread.is_alive())

    def test_every_sensitive_family_requires_the_ephemeral_token(self):
        cases = (
            ("POST", "/api/shutdown", None),
            ("POST", "/api/dsu/start", None),
            ("POST", "/api/dsu/stop", None),
            ("PUT", "/api/preferences", {"values": {"sync_interval": 30}}),
            ("PUT", "/api/manual/test", {"completed": True}),
            ("PUT", "/api/routes", {"routes": {}}),
            ("POST", "/api/routes/import", {"session": {}}),
            ("POST", "/api/manual/import", {"tracking": {}}),
            ("POST", "/api/backup/import", {"backup": {}}),
            ("GET", "/api/sync?force=1", None),
            ("GET", "/api/update?force=1", None),
        )
        with self.running_server() as (thread, port, dsu):
            for method, path, body in cases:
                with self.subTest(path=path):
                    status, _response, _headers = self.request(
                        port, method, path, body=body
                    )
                    self.assertEqual(status, 403)
            self.assertFalse(dsu.started)
            self.assertFalse(dsu.stopped)
            self.assertTrue(thread.is_alive())

    def test_valid_token_allows_mutation_but_json_requires_its_media_type(self):
        with self.running_server() as (_thread, port, dsu):
            headers = {SESSION_HEADER: self.TOKEN}
            status, _body, _response_headers = self.request(
                port,
                "PUT",
                "/api/preferences",
                body={"values": {"sync_interval": 30}},
                headers=headers,
            )
            self.assertEqual(status, 200)

            status, _body, _response_headers = self.request(
                port,
                "PUT",
                "/api/preferences",
                body={"values": {"sync_interval": 60}},
                headers={**headers, "Content-Type": "text/plain"},
            )
            self.assertEqual(status, 415)

            status, _body, _response_headers = self.request(
                port, "POST", "/api/dsu/start", headers=headers
            )
            self.assertEqual(status, 200)
            self.assertTrue(dsu.started)

    def test_session_token_changes_at_each_server_start(self):
        with self.running_server(token=None) as (_thread, port, _dsu):
            first = self.get_json(port, "/api/version")[1]["session_token"]
        with self.running_server(token=None) as (_thread, port, _dsu):
            second = self.get_json(port, "/api/version")[1]["session_token"]
        self.assertNotEqual(first, second)
        self.assertGreaterEqual(len(first), 40)

    def test_both_native_launchers_still_stop_the_server_cleanly(self):
        for name, shutdown in (
            ("Windows", windows_shutdown),
            ("macOS", macos_shutdown),
        ):
            with self.subTest(launcher=name):
                with self.running_server() as (thread, port, _dsu):
                    self.assertTrue(shutdown(port, self.TOKEN))
                    thread.join(timeout=3)
                    self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
