"""Verify browser CI phase deadlines without waiting for real timeouts."""
from pathlib import Path
import shutil
import subprocess
import unittest


class BrowserWatchdogTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is needed for browser deadline tests")
    def test_phase_deadlines(self):
        result = subprocess.run(
            [shutil.which("node"), "--test", str(Path(__file__).with_name("browser_watchdog.cjs"))],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
