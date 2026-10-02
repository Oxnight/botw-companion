"""Verify immediate port reuse and safe startup during shutdown."""

from http.server import BaseHTTPRequestHandler
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from botw_companion import __version__
from botw_companion.lifecycle import (
    loopback_port_available, open_loopback, resolve_loopback_startup,
)
from botw_companion.server import LoopbackThreadingHTTPServer


class ResponseHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *_args):
        pass


class LoopbackRelaunchTests(unittest.TestCase):
    def test_an_active_unrelated_listener_is_never_reported_free(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            self.assertFalse(loopback_port_available(listener.getsockname()[1]))

    @unittest.skipIf(os.name == "nt", "POSIX TIME_WAIT reuse policy")
    def test_rebind_immediately_after_a_clean_http_shutdown(self):
        for _ in range(3):
            server = LoopbackThreadingHTTPServer(("127.0.0.1", 0), ResponseHandler)
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01})
            thread.start()
            try:
                with open_loopback(f"http://127.0.0.1:{port}", timeout=2) as response:
                    self.assertEqual(response.read(), b"ok")
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()
            self.assertTrue(loopback_port_available(port))
            replacement = LoopbackThreadingHTTPServer(("127.0.0.1", port), ResponseHandler)
            replacement.server_close()

    @unittest.skipIf(os.name == "nt", "POSIX TIME_WAIT reuse policy")
    def test_rebind_immediately_after_the_process_is_killed(self):
        root = Path(__file__).resolve().parents[1]
        script = """
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import sys
from botw_companion.server import LoopbackThreadingHTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Length', '2')
        self.end_headers()
        self.wfile.write(b'ok')
    def log_message(self, *args):
        pass
server = LoopbackThreadingHTTPServer(('127.0.0.1', 0), Handler)
Path(sys.argv[1]).write_text(str(server.server_address[1]))
server.serve_forever()
"""
        with tempfile.TemporaryDirectory() as temporary:
            ready = Path(temporary) / "port.txt"
            process = subprocess.Popen([sys.executable, "-c", script, str(ready)], cwd=root,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(ready.exists(), "The child server did not start")
                port = int(ready.read_text())
                with open_loopback(f"http://127.0.0.1:{port}", timeout=2) as response:
                    self.assertEqual(response.read(), b"ok")
                process.kill()
                process.wait(timeout=3)
                self.assertTrue(loopback_port_available(port))
                replacement = LoopbackThreadingHTTPServer(("127.0.0.1", port), ResponseHandler)
                replacement.server_close()
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=3)

    def test_a_live_instance_is_reused_without_any_wait(self):
        identity = {"application": "BOTW Companion", "version": __version__}
        result = resolve_loopback_startup(8765, probe=lambda *args, **kwargs: identity,
                                         available=lambda port: self.fail("Must not bind a live server"),
                                         sleep=lambda seconds: self.fail("Must not wait for a live server"))
        self.assertEqual(result, (identity, False))

    def test_a_closing_instance_is_not_reopened(self):
        clock = [0.0]
        sleeps = []
        closing = {"lifecycle": {"shutdown_reason": "bouton_quitter"}}

        def sleep(seconds):
            sleeps.append(seconds)
            clock[0] += seconds

        result = resolve_loopback_startup(
            8765, probe=lambda *args, **kwargs: closing if clock[0] < .1 else None,
            available=lambda port: clock[0] >= .1,
            clock=lambda: clock[0], sleep=sleep,
        )
        self.assertEqual(result, (None, True))
        self.assertEqual(len(sleeps), 2)

    def test_an_unidentified_listener_is_left_alone_after_a_bounded_wait(self):
        clock = [0.0]

        def sleep(seconds):
            clock[0] += seconds

        result = resolve_loopback_startup(
            8765, probe=lambda *args, **kwargs: None, available=lambda port: False,
            clock=lambda: clock[0], sleep=sleep, timeout=.1,
        )
        self.assertEqual(result, (None, False))
        self.assertAlmostEqual(clock[0], .1)
