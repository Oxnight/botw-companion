"""Verify browser storage navigation does not accept failed or stale documents."""
from pathlib import Path
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from botw_companion.manual_tracking import ManualTrackingStore
from botw_companion.preferences import PreferenceStore
from botw_companion.route_sessions import RouteSessionStore
from botw_companion.runtime_state import RuntimeStateStore
from botw_companion.server import serve


class BrowserStorageNavigationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is needed for browser navigation tests")
    def test_navigation_evidence(self):
        result = subprocess.run(
            [shutil.which("node"), "--test", str(Path(__file__).with_name("browser_storage_navigation.cjs"))],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_initial_document_enforces_the_actual_origin_and_fetch_site_guards(self):
        class Captured(Exception):
            pass

        captured = []

        class Server:
            server_port = 18765
            server_name = '127.0.0.1'

            def __init__(self, address, handler):
                captured.append((handler, self))
                raise Captured()

        with tempfile.TemporaryDirectory(prefix='botw-navigation-') as directory:
            root = Path(directory)
            # Capture the real handler without binding a socket or starting services.
            with patch('botw_companion.server.LoopbackThreadingHTTPServer', Server), self.assertRaises(Captured):
                serve(lambda: {}, open_browser=False,
                      tracking_store=ManualTrackingStore(root / 'manual.json'),
                      route_store=RouteSessionStore(root / 'routes.json'),
                      preference_store=PreferenceStore(root / 'preferences.json'),
                      runtime_state_store=RuntimeStateStore(root / 'runtime.json'),
                      instance_guard=MagicMock(), dsu_manager=MagicMock(),
                      update_checker=MagicMock(), update_download_manager=MagicMock(),
                      update_installer=MagicMock(), browser_handoff=MagicMock(),
                      session_token='synthetic-token')
            handler, server = captured[0]
            cases = [
                ({}, None),
                ({'Sec-Fetch-Site': 'none'}, None),
                ({'Origin': 'http://127.0.0.1:18765', 'Sec-Fetch-Site': 'same-origin'}, None),
                ({'Origin': 'null', 'Sec-Fetch-Site': 'cross-site'}, 'Origine non autorisée'),
                ({'Sec-Fetch-Site': 'cross-site'}, 'Contexte de navigation non autorisé'),
                ({'Origin': 'http://127.0.0.1:18765', 'Sec-Fetch-Site': 'cross-site'},
                 'Contexte de navigation non autorisé'),
            ]
            for headers, rejection in cases:
                with self.subTest(headers=headers):
                    request = ('GET /?lang=fr HTTP/1.1\r\nHost: 127.0.0.1:18765\r\nConnection: close\r\n' +
                               ''.join(f'{key}: {value}\r\n' for key, value in headers.items()) + '\r\n').encode()
                    output = io.BytesIO()

                    class Connection:
                        def makefile(self, *args):
                            return io.BytesIO(request)

                        def sendall(self, value):
                            output.write(value)

                        def settimeout(self, timeout):
                            pass

                    handler(Connection(), ('127.0.0.1', 1234), server)
                    head, body = output.getvalue().split(b'\r\n\r\n', 1)
                    status = int(head.split()[1])
                    self.assertEqual(status, 403 if rejection else 200)
                    if rejection:
                        self.assertEqual(json.loads(body), {'erreur': rejection})
                    else:
                        self.assertIn(b'<html lang="fr"', body)
                    self.assertIn(b'X-Frame-Options: DENY', head)
