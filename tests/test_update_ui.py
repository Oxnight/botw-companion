"""Exercise the production update button handoff in Node."""

from pathlib import Path
import shutil
import subprocess
import unittest


class UpdateUITests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is needed for update UI tests")
    def test_update_actions(self):
        result = subprocess.run(
            [shutil.which("node"), "--test", str(Path(__file__).with_name("update_ui.cjs"))],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
