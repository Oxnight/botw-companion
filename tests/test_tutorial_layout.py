"""Exercise the production tour geometry and transition lifecycle in Node."""

from pathlib import Path
import shutil
import subprocess
import unittest


class TutorialLayoutTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is needed for tour layout tests")
    def test_javascript_layout_and_transitions(self):
        script = Path(__file__).with_name("tutorial_layout.cjs")
        result = subprocess.run(
            [shutil.which("node"), "--test", str(script)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
