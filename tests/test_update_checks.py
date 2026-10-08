"""Verify automatic and manual update check recovery in both languages."""
from pathlib import Path
import shutil
import subprocess
import unittest


class UpdateCheckTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is needed for update checks")
    def test_update_check_recovery(self):
        result = subprocess.run(
            [shutil.which("node"), "--test", str(Path(__file__).with_name("update_checks.cjs"))],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
