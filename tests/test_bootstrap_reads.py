"""Exercise bounded startup reads in both generated language variants."""
from pathlib import Path
import shutil
import subprocess
import unittest


class BootstrapReadTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is needed for bootstrap tests")
    def test_startup_reads(self):
        result = subprocess.run(
            [shutil.which("node"), "--test", str(Path(__file__).with_name("bootstrap_reads.cjs"))],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
