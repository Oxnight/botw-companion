"""Verify browser storage navigation does not accept failed or stale documents."""
from pathlib import Path
import shutil
import subprocess
import unittest


class BrowserStorageNavigationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is needed for browser navigation tests")
    def test_navigation_evidence(self):
        result = subprocess.run(
            [shutil.which("node"), "--test", str(Path(__file__).with_name("browser_storage_navigation.cjs"))],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
