import unittest
from collections import Counter

from botw_companion.analyzer import analyze
from botw_companion.resources import load_boss_reference


class BossSolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = load_boss_reference()
        cls.report = analyze({})
        cls.persistent = [item for item in cls.report["elements"] if item.get("boss_detail")]
        cls.map_combat = [item for item in cls.report["map_layers"] if item.get("boss_detail")]

    def test_reference_covers_every_documented_combat_point(self):
        self.assertEqual(self.reference["audit"]["strategies"], 21)
        self.assertEqual(self.reference["audit"]["persistent_bosses"], 84)
        self.assertEqual(self.reference["audit"]["map_combat_points"], 284)
        self.assertEqual(self.reference["audit"]["scripted_bosses_already_complete"], 13)

    def test_every_persistent_miniboss_has_a_complete_level_three_guide(self):
        self.assertEqual(len(self.persistent), 84)
        for item in self.persistent:
            guide = item["guide"]
            self.assertEqual(guide["quality_level"], 3, item["name"])
            self.assertGreaterEqual(len(guide["detailed_steps"]), 5, item["name"])
            self.assertTrue(guide["prerequisites"], item["name"])
            self.assertTrue(guide["preparation"], item["name"])
            self.assertTrue(guide["rewards"], item["name"])
            self.assertTrue(guide["sources"], item["name"])
            self.assertTrue(guide["boss_profile"]["weak_point"], item["name"])

    def test_persistent_variants_match_the_object_map(self):
        self.assertEqual(Counter(item["subtype"] for item in self.persistent), Counter({
            "Cryorok": 17, "Hinox bleu": 16, "Lithorok": 11, "Stalhinox": 10,
            "Hinox": 7, "Hinox noir": 7, "Lithorok nox": 7, "Magrok": 5,
            "Moldarquor": 4,
        }))

    def test_every_map_combat_point_has_a_complete_level_three_guide(self):
        self.assertEqual(len(self.map_combat), 284)
        for item in self.map_combat:
            guide = item["guide"]
            self.assertEqual(guide["quality_level"], 3, item["name"])
            self.assertGreaterEqual(len(guide["detailed_steps"]), 5, item["name"])
            self.assertTrue(guide["rewards"], item["name"])
            self.assertTrue(guide["sources"], item["name"])
            self.assertTrue(guide["boss_profile"]["weak_point"], item["name"])

    def test_lynel_and_guardian_variants_are_not_flattened(self):
        variants = Counter(item["guide"]["boss_profile"]["variant"] for item in self.map_combat)
        expected = {
            "Lynel": 6, "Lynel bleu": 7, "Lynel blanc": 9, "Lynel évolutif": 1,
            "Gardien détérioré": 55, "Gardien à pied": 46, "Gardien volant": 32,
            "Gardien tourelle": 21, "Nano Gardien 2.0": 6,
            "Nano Gardien 3.0": 6, "Nano Gardien 4.0": 9,
        }
        for subtype, count in expected.items():
            self.assertEqual(variants[subtype], count, subtype)

    def test_scaling_lynel_is_explicitly_documented(self):
        scaling = [
            item for item in self.map_combat
            if item["guide"]["boss_profile"]["variant"] == "Lynel évolutif"
        ]
        self.assertEqual(len(scaling), 1)
        self.assertTrue(scaling[0]["guide"]["boss_profile"]["scaling"])

    def test_public_audit_and_interface_expose_boss_coverage(self):
        audit = self.report["audit_guides"]
        self.assertEqual(audit["boss_scenarises_niveau_3"], 13)
        self.assertEqual(audit["mini_boss_permanents_niveau_3"], 84)
        self.assertEqual(audit["points_combat_farm_niveau_3"], 284)
        self.assertEqual(audit["solutions_completes_invalides"], [])
        with open("botw_companion/web/app.js", encoding="utf-8") as stream:
            script = stream.read()
        self.assertIn("guideBoss", script)
        self.assertIn("boss_profile", script)


if __name__ == "__main__":
    unittest.main()