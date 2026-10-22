from pathlib import Path
import subprocess
import unittest

from tools.browser_test_server import BrowserTestDsu, BrowserTestSync, build_report


class BrowserHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = build_report()

    def test_update_fixture_localization_bootstrap(self):
        result = subprocess.run(
            ["node", "--test", str(Path(__file__).with_name("browser_update_bootstrap.cjs"))],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_browser_launch_isolation(self):
        result = subprocess.run(
            ["node", "--test", str(Path(__file__).with_name("browser_launch.cjs"))],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_report_exercises_windows_sync_and_blood_moon_widgets(self):
        self.assertEqual(self.report["sauvegarde"]["plateforme"], "Windows")
        self.assertEqual(self.report["synchronisation"]["status"], "a_jour")
        self.assertTrue(self.report["lune_de_sang"]["available"])
        self.assertGreater(self.report["lune_de_sang"]["active_seconds_until_event"], 0)
        self.assertTrue(self.report["elements"])
        self.assertTrue(self.report["map_layers"])

    def test_fake_sync_never_changes_the_catalog_revision(self):
        controller = BrowserTestSync(self.report)
        checked = controller.check(force=True, include_report=True)
        self.assertFalse(checked["changed"])
        self.assertIs(checked["report"], self.report)
        self.assertEqual(
            checked["synchronisation"]["fingerprint"],
            "browser-test-report",
        )

    def test_fake_dsu_exercises_start_ready_stop_cycle(self):
        manager = BrowserTestDsu()
        self.assertEqual(manager.status()["state"], "stopped")
        self.assertEqual(manager.start()["state"], "ready")
        self.assertTrue(manager.status()["protocol_ready"])
        self.assertEqual(manager.status()["diagnostic"]["status"], "excellent")
        self.assertAlmostEqual(manager.status()["telemetry"]["received_hz"], 199.8)
        self.assertEqual(manager.stop()["state"], "stopped")


if __name__ == "__main__":
    unittest.main()
