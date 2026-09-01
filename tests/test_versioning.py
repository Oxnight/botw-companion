import subprocess
import sys
import unittest
from pathlib import Path


class VersioningTests(unittest.TestCase):
    def test_every_distributed_version_is_consistent(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(root / "tools" / "check_version_consistency.py")],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
