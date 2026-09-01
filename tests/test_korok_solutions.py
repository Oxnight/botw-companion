import unittest

from botw_companion.analyzer import analyze
from botw_companion.resources import load_catalog, load_korok_reference


class KorokSolutionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = load_korok_reference()
        cls.report = analyze({})
        cls.koroks = cls.report["categories"]["korogus"]["elements"]

    def test_reference_covers_every_catalog_korok_once(self):
        catalog = load_catalog()["koroks"]
        entries = self.reference["entries"]
        self.assertEqual((len(catalog), len(entries)), (900, 900))
        self.assertEqual({item["flag"] for item in catalog}, set(entries))
        self.assertEqual(len({entry["save_hash"] for entry in entries.values()}), 900)
        self.assertEqual(len({entry["object_hash"] for entry in entries.values()}), 900)
        self.assertEqual(len({entry["map_id"] for entry in entries.values()}), 900)
        self.assertTrue(all(1 <= entry["guide_id"] <= 900 for entry in entries.values()))
        for item in catalog:
            detail = entries[item["flag"]]
            self.assertLess(abs(item["x"] - detail["x"]), 0.02)
            self.assertLess(abs(item["z"] - detail["z"]), 0.02)

    def test_all_33_verified_puzzle_types_have_french_complete_solutions(self):
        entries = self.reference["entries"].values()
        self.assertEqual(self.reference["audit"]["types"], 33)
        self.assertEqual(sum(self.reference["audit"]["type_counts"].values()), 900)
        self.assertEqual(len({entry["puzzle_type"] for entry in entries}), 33)
        self.assertTrue(all(entry["puzzle_label"] for entry in entries))
        self.assertTrue(all(len(entry["steps"]) >= 3 for entry in entries))
        self.assertTrue(all(entry["requirements"] for entry in entries))

    def test_published_routes_are_complete_and_exposed_to_the_map(self):
        entries = self.reference["entries"].values()
        routed = [entry for entry in entries if entry.get("geo_points")]
        self.assertEqual(len(routed), 97)
        self.assertTrue(all(len(entry["geo_points"]) >= 2 for entry in routed))
        report_routed = [item for item in self.koroks
                         if item["guide"]["korok_reference"]["path_points"] >= 2]
        self.assertEqual(len(report_routed), 97)
        self.assertTrue(all(len(item["geo_points"]) >= 2 for item in report_routed))

    def test_every_runtime_guide_is_individual_verified_and_complete(self):
        self.assertEqual(len(self.koroks), 900)
        for item in self.koroks:
            with self.subTest(flag=item["flag"]):
                guide = item["guide"]
                self.assertEqual(guide["specificity"], "verified_korok_puzzle")
                self.assertEqual(guide["quality_level"], 3)
                self.assertGreaterEqual(len(guide["detailed_steps"]), 3)
                self.assertTrue(guide["mechanic"])
                self.assertEqual(guide["rewards"], ["1 noix korogu"])
                self.assertGreaterEqual(len(guide["sources"]), 3)
                self.assertNotIn("pas contenu", " ".join(guide["warnings"]).lower())

    def test_report_audit_states_the_full_verified_coverage(self):
        audit = self.report["audit_guides"]
        self.assertEqual(audit["korogus_solution_individuelle_verifiee"], 900)
        self.assertEqual(audit["korogus_avec_parcours_cartographique"], 97)
        self.assertEqual(audit["types_enigmes_korogus"], 33)
        self.assertEqual(audit["solutions_completes_invalides"], [])


if __name__ == "__main__":
    unittest.main()