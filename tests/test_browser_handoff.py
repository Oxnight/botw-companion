import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from botw_companion.browser_handoff import BrowserHandoff, await_browser_handoff
from botw_companion.lifecycle import open_loopback
import test_server_security as server_fixture


CLIENT = 'original-browser-client-1234'
OTHER = 'fallback-browser-client-5678'


class BrowserHandoffTests(unittest.TestCase):
    def test_persisted_handoff_survives_restart_and_has_one_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'handoff.json'
            first = BrowserHandoff(path)
            handoff = first.prepare(CLIENT, 8765, 'old-token')
            second = BrowserHandoff(path)
            self.assertIsNone(second.status(8765, 'old-token'))
            self.assertIsNone(second.status(9000, 'new-token'))
            self.assertIsNone(second.claim(8765, 'new-token', 'wrong', CLIENT))
            self.assertIsNone(second.claim(8765, 'new-token', handoff['id'], OTHER)['claimed_by'])
            self.assertEqual(second.claim(8765, 'new-token', handoff['id'], CLIENT)['claimed_by'], CLIENT)
            self.assertEqual(second.claim(8765, 'new-token', handoff['id'], OTHER)['claimed_by'], CLIENT)
            # A later ordinary restart must not suppress its browser opening.
            self.assertIsNone(second.status(8765, 'another-session'))

    def test_missing_tab_fallback_and_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            store = BrowserHandoff(Path(directory) / 'handoff.json')
            handoff = store.prepare(CLIENT, 8765, 'old-token')
            store.release(8765, 'old-token')
            self.assertEqual(store.status(8765, 'rollback-token')['client_id'], CLIENT)
            store.release(8765, 'rollback-token')
            state = store.claim(8765, 'rollback-token', handoff['id'], OTHER)
            self.assertEqual(state['claimed_by'], OTHER)
            self.assertEqual(store.claim(8765, 'rollback-token', handoff['id'], CLIENT)['claimed_by'], OTHER)

    def test_invalid_expired_and_cancelled_records_are_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'handoff.json'
            store = BrowserHandoff(path, clock=lambda: 1000)
            with self.assertRaises(ValueError):
                store.prepare('short', 8765, 'old')
            store.prepare(CLIENT, 8765, 'old')
            self.assertIsNone(BrowserHandoff(path, clock=lambda: 1601).status(8765, 'new'))
            store.cancel(); self.assertIsNone(store.status(8765, 'new'))
            path.write_text('{"port":8765,"created_at":1000}')
            self.assertIsNone(store.status(8765, 'new'))

    def test_launcher_reuses_only_acknowledged_handoff_and_releases_timeout(self):
        calls = []
        identity = {'application': 'BOTW Companion', 'session_token': 'new',
                    'browser_handoff': {'id': 'handoff', 'claimed_by': None}}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def read(self):
                return json.dumps({**identity, 'browser_handoff': {'id': 'handoff', 'claimed_by': CLIENT}}).encode()
        def opener(request, timeout):
            calls.append(request); return Response()
        self.assertTrue(await_browser_handoff(8765, identity, opener=opener, sleep=lambda _: None))
        calls.clear()
        self.assertFalse(await_browser_handoff(8765, identity, opener=opener, timeout=0))
        self.assertEqual(calls[0].full_url, 'http://127.0.0.1:8765/api/browser/release')
        self.assertEqual(calls[0].get_header('X-botw-session-token'), 'new')
        self.assertFalse(await_browser_handoff(8765, {}))

    def test_claim_api_enforces_authentication_and_rotates_session(self):
        with tempfile.TemporaryDirectory() as directory:
            store = BrowserHandoff(Path(directory) / 'handoff.json')
            with patch('botw_companion.server.BrowserHandoff', return_value=store):
                fixture = server_fixture.ServerSecurityTests()
                with fixture.running_server() as values:
                    # The fixture exposes (thread, port, dsu).
                    port = values[1]
                    handoff = store.prepare(CLIENT, port, 'previous-session')
                    url = f'http://127.0.0.1:{port}'
                    with open_loopback(url + '/browser_session.js') as response:
                        self.assertIn('text/javascript', response.headers['Content-Type'])
                        self.assertIn(b'BOTWBrowserSession', response.read())
                    with open_loopback(url + '/api/version') as response:
                        identity = json.loads(response.read())
                    self.assertEqual(identity['browser_handoff']['id'], handoff['id'])
                    body = json.dumps({**handoff}).encode()
                    bad = Request(url + '/api/browser/claim', body,
                                  {'Content-Type': 'application/json'}, method='POST')
                    with self.assertRaises(HTTPError) as error:
                        open_loopback(bad)
                    self.assertEqual(error.exception.code, 403)
                    good = Request(url + '/api/browser/claim', body,
                                   {'Content-Type': 'application/json',
                                    'X-BOTW-Session-Token': fixture.TOKEN}, method='POST')
                    with open_loopback(good) as response:
                        claimed = json.loads(response.read())
                    self.assertEqual(claimed['browser_handoff']['claimed_by'], CLIENT)

    def test_both_native_launchers_suppress_duplicate_open_only_after_ack(self):
        from botw_companion import macos_launcher, windows_launcher
        for module in (macos_launcher, windows_launcher):
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as directory:
                identity = {'application': 'BOTW Companion', 'version': module.__version__, 'session_token': 'new'}
                with patch.object(module, 'companion_data_dir', return_value=Path(directory)), \
                     patch.object(module, 'resolve_loopback_startup', return_value=(None, True)), \
                     patch.object(module, 'launch_server'), \
                     patch.object(module, 'wait_until_ready', return_value=identity), \
                     patch.object(module, 'await_browser_handoff', return_value=True) as reuse:
                    browser = unittest.mock.Mock()
                    module.run(browser=browser, frozen=True)
                    reuse.assert_called_once_with(8765, identity)
                    browser.assert_not_called()
