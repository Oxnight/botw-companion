from contextlib import contextmanager
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from socketserver import _SocketWriter
from unittest.mock import patch
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

    def test_native_language_requires_authorization_and_preserves_preferences(self):
        with self.running_server() as (_thread, port, _dsu):
            preferences = self.get_json(port, '/api/preferences')[1]
            status, _, _ = self.request(port, 'PUT', '/api/language', body={'language': 'en'})
            self.assertEqual(status, 403)
            self.assertEqual(self.get_json(port, '/api/language')[1], {'language': 'fr'})
            for language in ('en', 'fr'):
                status, body, _ = self.request(port, 'PUT', '/api/language', body={'language': language},
                                              headers={SESSION_HEADER: self.TOKEN})
                self.assertEqual((status, json.loads(body)), (200, {'language': language}))
                self.assertEqual(self.get_json(port, '/api/language')[1], json.loads(body))
            for value in ([], {}, True, None, '../../en', 'de'):
                status, body, _ = self.request(port, 'PUT', '/api/language', body={'language': value},
                    headers={SESSION_HEADER: self.TOKEN, 'X-BOTW-Language': 'en'})
                self.assertEqual(status, 400)
                self.assertEqual(json.loads(body)['erreur'], 'Invalid language')
            with patch('botw_companion.server.remember_language', side_effect=OSError('disk full')):
                status, body, _ = self.request(port, 'PUT', '/api/language', body={'language': 'en'},
                    headers={SESSION_HEADER: self.TOKEN, 'X-BOTW-Language': 'en'})
                self.assertEqual(status, 503)
                self.assertNotIn('n’a pas', json.loads(body)['erreur'])
            self.assertEqual(self.get_json(port, '/api/preferences')[1], preferences)

    def test_non_ascii_and_duplicate_session_headers_are_rejected(self):
        with self.running_server() as (_thread, port, dsu):
            for tokens in (("é",), (self.TOKEN, self.TOKEN)):
                with self.subTest(tokens=tokens):
                    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
                    try:
                        connection.putrequest('POST', '/api/dsu/start')
                        for token in tokens:
                            connection.putheader(SESSION_HEADER, token)
                        connection.putheader('Content-Length', '0')
                        connection.endheaders()
                        response = connection.getresponse()
                        self.assertEqual(response.status, 403)
                        response.read()
                    finally:
                        connection.close()
            self.assertFalse(dsu.started)

    def test_closed_shutdown_response_still_stops_the_server(self):
        original_write = _SocketWriter.write

        def disconnected(writer, body):
            if b'"status": "arret"' in body:
                raise BrokenPipeError('The browser closed its tab')
            return original_write(writer, body)

        diagnostic = io.StringIO()
        with self.running_server() as (thread, port, _dsu):
            with redirect_stderr(diagnostic), patch.object(_SocketWriter, 'write', disconnected):
                with self.assertRaises(http.client.IncompleteRead):
                    self.request(port, 'POST', '/api/shutdown', headers={SESSION_HEADER: self.TOKEN})
                thread.join(3)
            self.assertFalse(thread.is_alive())
            self.assertIn('BrokenPipeError', diagnostic.getvalue())

    def test_malformed_imports_return_json_errors_in_both_languages(self):
        with self.running_server() as (_thread, port, _dsu):
            for language in ('fr', 'en'):
                for method, path, payload in (
                    ('PUT', '/api/preferences', {'values': {'sync_interval': []}}),
                    ('POST', '/api/routes/import', {'session': {'steps': [None]}}),
                    ('POST', '/api/routes/import', {'session': {'start': {'x': 'NaN', 'z': 0}}}),
                    ('POST', '/api/manual/import', {'tracking': ManualTrackingStore._empty(), 'mode': []}),
                ):
                    with self.subTest(language=language, path=path, payload=payload):
                        status, body, headers = self.request(port, method, path, body=payload,
                            headers={SESSION_HEADER: self.TOKEN, 'X-BOTW-Language': language})
                        self.assertEqual(status, 400)
                        self.assertIn('erreur', json.loads(body))
                        self.assertEqual(headers['Content-Language'], language)

    def test_invalid_json_numbers_encoding_and_depth_are_rejected(self):
        with self.running_server() as (_thread, port, _dsu):
            for body in (b'{"values":{"sync_interval":NaN}}',
                         b'{"values":{"sync_interval":' + b'1' * 5000 + b'}}',
                         b'[' * 1100 + b'0' + b']' * 1100,
                         b'{"note":"\\ud800"}', b'\xff'):
                with self.subTest(body=body[:60]):
                    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
                    try:
                        connection.request('PUT', '/api/preferences', body=body,
                            headers={SESSION_HEADER: self.TOKEN, 'Content-Type': 'application/json'})
                        response = connection.getresponse()
                        self.assertEqual(response.status, 400)
                        self.assertEqual(json.loads(response.read()), {'erreur': 'JSON invalide'})
                    finally:
                        connection.close()

    def test_incomplete_request_body_has_a_bounded_timeout(self):
        with self.running_server() as (_thread, port, _dsu):
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=14)
            try:
                connection.request('PUT', '/api/preferences', body=b'{', headers={
                    SESSION_HEADER: self.TOKEN, 'Content-Type': 'application/json', 'Content-Length': '100'})
                response = connection.getresponse()
                self.assertEqual(response.status, 408)
                self.assertEqual(json.loads(response.read()), {'erreur': 'Requête interrompue ou incomplète'})
            finally:
                connection.close()

    @contextmanager
    def running_server(self, *, token: str | None = TOKEN, payload_factory=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            if payload_factory is not None:
                (root / "routes.json").write_text(json.dumps(RouteSessionStore._empty()), encoding="utf-8")
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
                args=(payload_factory or (lambda: {}),),
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

    def test_primary_theme_is_embedded_in_each_language_document(self):
        import re

        with self.running_server() as (_thread, port, _dsu):
            _, css, _ = self.request(port, "GET", "/style.css")
            # Text-mode source reads normalize checkout line endings.
            expected = css.decode().replace("\r\n", "\n").replace("\r", "\n")
            self.assertIn("padding: 10px 12px", expected)
            self.assertIn("#search:focus-visible", expected)
            for language in ("fr", "en", "fr"):
                with self.subTest(language=language):
                    status, body, headers = self.request(
                        port, "GET", "/?lang=" + language
                    )
                    text = body.decode()
                    self.assertEqual(status, 200)
                    self.assertIn('lang="' + language + '"', text)
                    embedded = re.search(
                        r'<style id="application-style">(.*?)</style>',
                        text, re.S,
                    )
                    self.assertIsNotNone(embedded)
                    self.assertEqual(embedded.group(1), expected)
                    self.assertNotIn('<link rel="stylesheet" href="/style.css">', text)
                    self.assertNotIn('id="search" style=', text)
                    self.assertIn(':root', embedded.group(1))
                    self.assertIn('--text:', embedded.group(1))
                    self.assertIn('--gold:', embedded.group(1))
                    self.assertIn('type="search"', text)
                    self.assertEqual(headers["Cache-Control"], "no-store")

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
        # Keep this test focused on authorization. The server intentionally
        # rejects an invalid token before parsing a request body. Leaving such
        # a body unread while returning HTTP 403 can make Windows reset the
        # HTTP/1.0 connection before urllib receives the response.
        cases = (
            ("POST", "/api/shutdown"),
            ("POST", "/api/dsu/start"),
            ("POST", "/api/dsu/stop"),
            ("PUT", "/api/preferences"),
            ("PUT", "/api/manual/test"),
            ("PUT", "/api/routes"),
            ("POST", "/api/routes/import"),
            ("POST", "/api/manual/import"),
            ("POST", "/api/backup/import"),
            ("GET", "/api/sync?force=1"),
            ("GET", "/api/update?force=1"),
            ("GET", "/api/update/download"),
            ("POST", "/api/update/download/start"),
            ("POST", "/api/update/download/retry"),
            ("POST", "/api/update/download/cancel"),
            ("POST", "/api/update/install"),
        )
        with self.running_server() as (thread, port, dsu):
            for method, path in cases:
                with self.subTest(path=path):
                    status, _response, _headers = self.request(port, method, path)
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
