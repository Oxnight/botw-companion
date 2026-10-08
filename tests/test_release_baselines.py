from contextlib import redirect_stderr
from io import StringIO
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from botw_companion.manual_tracking import ManualTrackingStore
from botw_companion.preferences import PreferenceStore
from botw_companion.route_sessions import RouteSessionStore
from botw_companion.versioning import ReleaseVersion
from tools.check_version_consistency import literal_version_errors
from tools.release_metadata import main as release_metadata_main, metadata
from tools.seed_installation_data import FIXTURE, seed
from tools.upgrade_baselines import FIRST_STABLE, resolve_baselines


ROOT = Path(__file__).resolve().parents[1]


class UpgradeBaselinePolicyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.reference_root = Path(temporary.name)
        (self.reference_root / "packaging").mkdir()
        self.baseline_path = self.reference_root / "packaging/UPGRADE_BASELINE"
        self.baseline_path.write_text(FIRST_STABLE.display)
        for name, value in (("ROOT", self.reference_root), ("CURRENT_VERSION", FIRST_STABLE)):
            mock = patch("tools.release_metadata."+name, value)
            mock.start()
            self.addCleanup(mock.stop)

    def test_bootstrap_requires_no_previous_release_or_remote_lookup(self):
        with patch("subprocess.run", side_effect=AssertionError("remote lookup")):
            values = metadata()
        self.assertEqual(values["installation_validation"], "bootstrap")
        self.assertEqual(values["prerelease"], "false")
        for prefix in ("upgrade", "minimum_upgrade"):
            for key in ("version", "tag", "installer_name", "dmg_name"):
                self.assertEqual(values[f"{prefix}_{key}"], "")

    def test_first_update_uses_first_stable_without_duplicate_native_run(self):
        previous, minimum = resolve_baselines(ReleaseVersion.parse("1.0.1"), FIRST_STABLE)
        self.assertEqual(previous, FIRST_STABLE)
        self.assertIsNone(minimum)

    def test_later_updates_check_both_latest_stable_and_first_stable(self):
        previous, minimum = resolve_baselines(
            ReleaseVersion.parse("1.2.0"), ReleaseVersion.parse("1.1.0")
        )
        self.assertEqual(previous.tag, "v1.1.0")
        self.assertEqual(minimum, FIRST_STABLE)

    def test_future_metadata_exports_real_stable_asset_names(self):
        self.baseline_path.write_text("1.1.0")
        with patch("tools.release_metadata.CURRENT_VERSION", ReleaseVersion.parse("1.2.0")):
            values = metadata()
        self.assertEqual(values["installation_validation"], "upgrade")
        self.assertEqual(values["upgrade_tag"], "v1.1.0")
        self.assertEqual(values["upgrade_installer_name"], "BOTW_Companion_1.1.0_Setup.exe")
        self.assertEqual(values["upgrade_dmg_name"], "BOTW_Companion_1.1.0_macOS_arm64.dmg")
        self.assertEqual(values["minimum_upgrade_tag"], FIRST_STABLE.tag)
        self.assertEqual(values["minimum_upgrade_dmg_name"], FIRST_STABLE.dmg_name)

    def test_future_prerelease_still_requires_an_older_stable_reference(self):
        previous, minimum = resolve_baselines(ReleaseVersion.parse("1.1.0-rc.1"), FIRST_STABLE)
        self.assertEqual(previous, FIRST_STABLE)
        self.assertIsNone(minimum)

    def test_invalid_baselines_cannot_silently_bootstrap(self):
        for current, baseline in (
            ("1.0.0", "1.0.1"), ("1.0.1", "1.0.1"), ("1.0.1", "1.0.2"),
            ("1.0.1", "1.0.0-rc.1"), ("1.0.1", "0.9.0"),
            ("1.0.0-rc.1", "1.0.0"),
        ):
            with self.subTest(current=current, baseline=baseline), self.assertRaises(ValueError):
                resolve_baselines(ReleaseVersion.parse(current), ReleaseVersion.parse(baseline))

    def test_missing_or_invalid_reference_configuration_cannot_bootstrap(self):
        self.baseline_path.unlink()
        with self.assertRaises(FileNotFoundError):
            metadata()
        for value in ("", "bad", "1.0.0-rc.1", "0.9.0", "1.0.1"):
            with self.subTest(value=value):
                self.baseline_path.write_text(value)
                with self.assertRaises(ValueError):
                    metadata()

    def test_first_stable_tag_exports_bootstrap_metadata_without_a_remote_lookup(self):
        output = self.reference_root / "github-output"
        with patch("subprocess.run", side_effect=AssertionError("remote lookup")):
            self.assertEqual(release_metadata_main([
                "--tag", FIRST_STABLE.tag, "--github-output", str(output),
            ]), 0)
        values = dict(line.split("=", 1) for line in output.read_text().splitlines())
        self.assertEqual(values["display_version"], FIRST_STABLE.display)
        self.assertEqual(values["installation_validation"], "bootstrap")
        self.assertEqual(values["upgrade_tag"], "")
        self.assertEqual(values["minimum_upgrade_tag"], "")

    def test_wrong_tag_cannot_emit_release_metadata_outputs(self):
        output = self.reference_root / "github-output"
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
            release_metadata_main([
                "--tag", "not-a-release-tag", "--github-output", str(output),
            ])
        self.assertEqual(error.exception.code, 2)
        self.assertFalse(output.exists())


class ReleaseValidationTests(unittest.TestCase):
    def test_workflow_guards_all_four_downloads_but_always_runs_native_validation(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        blocks = re.split(r"^      - name: ", workflow, flags=re.MULTILINE)[1:]
        downloads = [b for b in blocks if "gh release download" in b]
        self.assertEqual(len(downloads), 4)
        for block in downloads:
            field = "minimum_upgrade_tag" if "minimum upgrade reference" in block else "upgrade_tag"
            self.assertIn(f"if: env.BUILD_PACKAGES == 'true' && steps.version.outputs.{field} != ''", block)
            self.assertIn('--repo "${{ github.repository }}"', block)
            self.assertNotIn("continue-on-error", block)
        main_runs = [b for b in blocks if b.startswith("Test installation,") or b.startswith("Test DMG,")]
        self.assertEqual(len(main_runs), 2)
        for block in main_runs:
            self.assertIn("if: env.BUILD_PACKAGES == 'true'\n", block)
            self.assertNotIn("continue-on-error", block)
        dispatch = workflow.split("  workflow_dispatch:\n", 1)[1].split("\nconcurrency:", 1)[0]
        self.assertEqual(re.findall(r"^      ([a-z_]+):$", dispatch, flags=re.MULTILINE),
                         ["validate_packages"])
        publish = workflow.split("  publish:\n", 1)[1]
        self.assertIn("if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')", publish)

    def test_native_bootstrap_retains_data_restart_rollback_and_interruption_checks(self):
        windows = (ROOT / "tools/test_windows_installation.ps1").read_text()
        macos = (ROOT / "tools/test_macos_installation.sh").read_text()
        self.assertIn('$PreviousInstallerPath = $resolvedInstaller', windows)
        self.assertIn('$metadata.installation_validation -ne "bootstrap"', windows)
        self.assertIn('\n    Test-AssistedUpdate $upgradeInstallRoot $upgradeDataRoot $resolvedInstaller 18769\n', windows)
        self.assertIn('-ValidateUpgradeData', windows)
        self.assertIn('"${PREVIOUS_DMG_PATH:-$DMG_PATH}"', macos)
        self.assertIn('$VALIDATION_MODE" != "bootstrap"', macos)
        for marker in ("BOTW_UPDATE_FORCE_RESTART_FAILURE=1", "BOTW_UPDATE_KILL_AFTER_SWAP=1",
                       'rollback_performed', 'assert_image_detached', 'invalid disk image',
                       '18769 yes', '18772 yes'):
            self.assertIn(marker, macos)
        for script in (windows, macos):
            self.assertIn('seed_installation_data.py', script)

    def test_shared_data_fixture_is_accepted_without_loss(self):
        payloads = json.loads(FIXTURE.read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed(root)
            original = {p.name: p.read_bytes() for p in root.iterdir()}
            manual = ManualTrackingStore(root / "manual_tracking.json").load()
            routes = RouteSessionStore(root / "route_sessions.json").load()
            preferences = PreferenceStore(root / "preferences.json").load()
            self.assertEqual(manual, payloads["manual_tracking.json"])
            session = routes["sessions"]["session-reference"]
            expected = payloads["route_sessions.json"]["sessions"]["session-reference"]
            self.assertEqual(routes["active_session_id"], "session-reference")
            self.assertEqual(session["name"], expected["name"])
            self.assertEqual(session["entries"][0]["tracking_id"], expected["entries"][0]["tracking_id"])
            self.assertTrue(session["entries"][0]["locked"])
            for key, value in expected["entries"][0]["snapshot"].items():
                self.assertEqual(session["entries"][0]["snapshot"][key], value)
            self.assertEqual(preferences, payloads["preferences.json"])
            self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, original)

    def test_version_audit_ignores_pycharm_metadata_but_checks_application_and_installer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (".idea/workspace.xml", "companion.iml"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('<component value="1.0.0"/>\n')
            self.assertEqual(literal_version_errors(root, FIRST_STABLE), [])
            for name in ("botw_companion/example.py", "windows/Companion.iss"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('APPLICATION_VERSION = "1.0.0"\n')
            self.assertEqual(len(literal_version_errors(root, FIRST_STABLE)), 2)

    def test_stable_version_audit_distinguishes_examples_references_and_application_constants(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("tests/example.py", "docs/process.md", "packaging/UPGRADE_BASELINE",
                         "node_modules/dependency/package.json", ".venv/dependency.py"):
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('"1.0.0"\n')
            p = root / "botw_companion/example.py"
            p.parent.mkdir(parents=True)
            p.write_text('EXAMPLE = "1.0.0-rc.1"\n')
            self.assertEqual(literal_version_errors(root, FIRST_STABLE), [])
            for value in ('"1.0.0"', '"v1.0.0"'):
                p.write_text('APPLICATION_VERSION = '+value+'\n')
                self.assertEqual(len(literal_version_errors(root, FIRST_STABLE)), 1)


if __name__ == "__main__":
    unittest.main()
