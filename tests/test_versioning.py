import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from botw_companion import __version__
from botw_companion.versioning import CURRENT_VERSION, ReleaseVersion


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

    def test_runtime_and_release_metadata_come_from_the_same_source(self):
        self.assertEqual(__version__, CURRENT_VERSION.pep440)
        self.assertEqual(CURRENT_VERSION.tag, f"v{CURRENT_VERSION.display}")
        self.assertEqual(
            CURRENT_VERSION.installer_name,
            f"BOTW_Companion_{CURRENT_VERSION.display}_Setup.exe",
        )
        self.assertEqual(
            CURRENT_VERSION.dmg_name,
            f"BOTW_Companion_{CURRENT_VERSION.display}_macOS_arm64.dmg",
        )

    def test_prerelease_and_stable_release_rules(self):
        alpha = ReleaseVersion.parse("2.3.4-alpha.7")
        beta = ReleaseVersion.parse("2.3.4-beta.2")
        candidate = ReleaseVersion.parse("2.3.4-rc.1")
        stable = ReleaseVersion.parse("2.3.4")
        self.assertEqual(alpha.pep440, "2.3.4a7")
        self.assertEqual(beta.pep440, "2.3.4b2")
        self.assertEqual(candidate.pep440, "2.3.4rc1")
        self.assertTrue(alpha.is_prerelease)
        self.assertFalse(stable.is_prerelease)
        self.assertEqual(stable.title, "BOTW Companion 2.3.4")
        self.assertLess(alpha.precedence, beta.precedence)
        self.assertLess(beta.precedence, candidate.precedence)
        self.assertLess(candidate.precedence, stable.precedence)
        as_tuple = lambda value: tuple(map(int, value.split(".")))
        self.assertLess(as_tuple(alpha.macos_bundle), as_tuple(beta.macos_bundle))
        self.assertLess(as_tuple(beta.macos_bundle), as_tuple(candidate.macos_bundle))
        self.assertLess(as_tuple(candidate.macos_bundle), as_tuple(stable.macos_bundle))

    def test_invalid_or_ambiguous_versions_are_rejected(self):
        for value in ("v1.0.0", "1.0", "1.0.0-dev.1", "01.0.0", "1.0.0-alpha.0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ReleaseVersion.parse(value)

    def test_metadata_exports_every_value_for_github_actions(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "github-output.txt"
            result = subprocess.run(
                [
                    sys.executable,
                    str(root / "tools" / "release_metadata.py"),
                    "--github-output",
                    str(output),
                    "--tag",
                    CURRENT_VERSION.tag,
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            values = dict(line.split("=", 1) for line in output.read_text().splitlines())
            self.assertEqual(values["display_version"], CURRENT_VERSION.display)
            self.assertEqual(
                values["prerelease"], str(CURRENT_VERSION.is_prerelease).lower()
            )
            self.assertEqual(values["installer_name"], CURRENT_VERSION.installer_name)
            self.assertEqual(values["dmg_name"], CURRENT_VERSION.dmg_name)

    def test_wrong_tag_stops_the_release_before_building(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                str(root / "tools" / "release_metadata.py"),
                "--tag",
                "v9.9.9",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(CURRENT_VERSION.tag, result.stderr)


if __name__ == "__main__":
    unittest.main()
