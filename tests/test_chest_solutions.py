import unittest
from collections import Counter

from botw_companion.analyzer import analyze
from botw_companion.resources import load_chest_reference


class ChestSolutionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = load_chest_reference()
        cls.report = analyze({})
        cls.world = cls.report["categories"]["coffres_monde"]["elements"]
        cls.dungeons = cls.report["categories"]["coffres_donjons"]["elements"]
        cls.shrines = cls.report["categories"]["coffres_sanctuaires"]["elements"]

    def test_reference_covers_every_chest_category(self):
        audit = self.reference["audit"]
        self.assertEqual(audit["world_chests"], 1361)
        self.assertEqual(audit["dungeon_chests"], 42)
        self.assertEqual(audit["shrine_entries"], 136)
        self.assertEqual(audit["physical_shrine_chests"], 205)

    def test_world_access_classification_is_complete_and_stable(self):
        self.assertEqual(self.reference["audit"]["world_access_types"], {
            "buried": 256, "burn_ivy": 2, "enemy_locked": 54,
            "event_locked": 24, "flying_platform": 118, "metal": 372,
            "rock_cover": 13, "stone": 294, "trial_room": 44, "wood": 184,
        })
        self.assertEqual(sum(self.reference["audit"]["world_access_types"].values()), 1361)

    def test_exact_world_accesses_have_complete_verified_guides(self):
        exact = [item for item in self.world if item["guide"]["specificity"] == "verified_chest_access"]
        self.assertEqual(len(exact), 443)
        self.assertTrue(all(item["guide"]["quality_level"] == 3 for item in exact))
        self.assertTrue(all(len(item["guide"]["detailed_steps"]) >= 5 for item in exact))
        self.assertTrue(all(item["guide"]["sources"] for item in exact))

    def test_family_world_methods_are_explicitly_level_two(self):
        family = [item for item in self.world if item["guide"]["specificity"] == "verified_chest_family"]
        self.assertEqual(len(family), 918)
        self.assertTrue(all(item["guide"]["quality_level"] == 2 for item in family))
        self.assertFalse(any("individuel confirmé" in item["guide"]["specificity_label"] for item in family))

    def test_every_world_chest_retains_objmap_position_and_altitude(self):
        self.assertEqual(len(self.world), 1361)
        for item in self.world:
            with self.subTest(hash=item["hash"]):
                if item.get("x") is not None:
                    self.assertIsInstance(item["x"], (int, float))
                    self.assertIsInstance(item["z"], (int, float))
                self.assertIsInstance(item["chest_access"]["y"], (int, float))

    def test_all_physical_shrine_chests_expose_position_and_access_context(self):
        details = [detail for item in self.shrines for detail in item["guide"]["chest_details"]]
        self.assertEqual(len(details), 205)
        self.assertTrue(all(detail["number"] >= 1 for detail in details))
        self.assertTrue(all(detail["area"] and detail["access_label"] and detail["access"] for detail in details))
        self.assertTrue(all(all(value is not None for value in detail["interior_position"].values())
                            for detail in details))

    def test_dungeon_chests_and_public_audit_expose_mechanisms(self):
        self.assertEqual(len(self.dungeons), 42)
        maps = Counter(item["interior_map"] for item in self.dungeons)
        self.assertEqual(set(maps), {"Vah'Ruta", "Vah'Rudania", "Vah'Medoh", "Vah'Naboris",
                                    "Épreuve finale de l'Épée"})
        self.assertTrue(all(item["interior_position"]["area"] for item in self.dungeons))
        self.assertTrue(all(item["guide"]["mechanic"] for item in self.dungeons))
        audit = self.report["audit_guides"]
        self.assertEqual(audit["coffres_monde_acces_individuel_verifie"], 443)
        self.assertEqual(audit["coffres_monde_methode_par_famille_verifiee"], 918)
        self.assertEqual(audit["coffres_donjons_position_interieure_et_mecanisme"], 42)
        self.assertEqual(audit["coffres_physiques_sanctuaires_documentes"], 205)


if __name__ == "__main__":
    unittest.main()