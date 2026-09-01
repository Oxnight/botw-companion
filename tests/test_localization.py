import unittest

from botw_companion.analyzer import analyze
from botw_companion.resources import (load_catalog, load_nomenclature_reference,
                                      load_solution_reference)


class FrenchLocalizationTests(unittest.TestCase):
    def test_reference_names_are_french(self):
        catalog = load_catalog()
        by_id = lambda group, key: next(x for x in catalog[group] if x["id"] == key)
        self.assertEqual(by_id("shrines", "Dungeon000")["name"], "Sanctuaire de Ta'Mur")
        self.assertEqual(by_id("main_quests", "destroyganon")["name"], "Abattre Ganon")
        self.assertEqual(by_id("side_quests", "miskothegreatbandit")["name"], "Le trésor de Lambda")
        self.assertEqual(by_id("memories", "apremonition")["name"], "Le présage")
        self.assertEqual(by_id("armor_owned", "Armor_116_Upper")["name"], "Tunique de Prodige")

    def test_localization_does_not_change_technical_ids(self):
        import json
        from importlib.resources import files
        localized = load_catalog()
        raw = json.loads(files("botw_companion.data").joinpath("catalog.json").read_text())
        for group in ("shrines", "main_quests", "side_quests", "compendium", "armor_owned"):
            self.assertEqual([x.get("id") for x in localized[group]], [x.get("id") for x in raw[group]])
            self.assertEqual([x.get("flag") for x in localized[group]], [x.get("flag") for x in raw[group]])

    def test_chest_contents_and_regions_are_localized(self):
        catalog = load_catalog()
        self.assertEqual(catalog["world_chests"][0]["contenu"], "Flèche de feu x10")
        self.assertEqual(catalog["shrines"][0]["region"], "Ordinn")
        self.assertEqual(catalog["compendium"][0]["name"], "Cheval")

    def test_localization_preserves_alternative_dlc_flags(self):
        catalog = load_catalog()
        arquor = next(item for item in catalog["scripted_bosses"] if item["id"] == "arquor-rex")
        self.assertIn("BalladOfHeroGerudo_FirstKillSandwormR", arquor["any_flags"])

    def test_step_seven_corrects_display_text_without_touching_ids(self):
        catalog = load_catalog()
        trials = catalog["trial_of_the_sword"]
        self.assertEqual(trials[0]["name"], "Épreuves basiques de l'épée")
        self.assertEqual(trials[0]["region"], "Épreuves de l'épée")
        self.assertEqual(next(x for x in catalog["malanya"] if x["id"] == "malanya")["name"],
                         "Réveiller Marlon")
        import json
        from importlib.resources import files
        raw = json.loads(files("botw_companion.data").joinpath("catalog.json").read_text())
        self.assertEqual(catalog["map_layers"][0]["id"], raw["map_layers"][0]["id"])
        self.assertEqual(catalog["map_layers"][0]["acteur"], raw["map_layers"][0]["acteur"])

    def test_corrective_step_six_has_an_independent_french_reference(self):
        reference = load_nomenclature_reference()
        self.assertEqual(reference["schema_version"], 1)
        self.assertEqual(reference["locale"], "fr-FR")
        self.assertGreaterEqual(len(reference["exact"]), 100)
        self.assertTrue(reference["forbidden_visible_tokens"])
        self.assertTrue(reference["sources"])

    def test_corrective_step_six_translates_all_external_quest_facts(self):
        report = analyze({})
        quests = [item for category in ("quetes_principales", "quetes_sanctuaires", "quetes_secondaires")
                  for item in report["categories"][category]["elements"]]
        visible = [text for item in quests for text in (
            item["name"], item["guide"].get("quest_giver", ""),
            *item["guide"]["rewards"], *item["guide"]["prerequisites"],
            *item["guide"]["preparation"],
        )]
        forbidden = load_nomenclature_reference()["forbidden_visible_tokens"]
        self.assertFalse(any(token.lower() in text.lower() for token in forbidden for text in visible))
        joined = "\n".join(visible)
        self.assertIn("Couronne de Midona", joined)
        self.assertIn("Chausses de Tingle", joined)
        self.assertIn("Masque spectral", joined)
        self.assertIn("Destrier de légende 0.1 ; Photo des Prodiges", joined)

    def test_all_changed_character_names_use_french_european_names(self):
        report = analyze({})
        quests = [item for category in ("quetes_principales", "quetes_sanctuaires", "quetes_secondaires")
                  for item in report["categories"][category]["elements"]]
        by_internal_id = {item.get("quest_internal_id"): item for item in quests}
        reference = load_nomenclature_reference()["exact"]
        raw_facts = load_solution_reference()["quest_facts"]
        checked = 0
        for internal_id, facts in raw_facts.items():
            giver = facts.get("giver")
            if not giver or internal_id not in by_internal_id:
                continue
            expected_name = reference.get(giver, giver)
            item = by_internal_id[internal_id]
            self.assertEqual(item["quest_facts"]["giver"], expected_name)
            self.assertEqual(item["guide"]["quest_giver"], expected_name)
            checked += 1
        self.assertGreaterEqual(checked, 100)

        givers = {(item.get("guide") or {}).get("quest_giver") for item in quests}
        facts = {item.get("quest_facts", {}).get("giver") for item in quests}
        expected = {"Noïa", "Asarim", "Pru'ha", "Kangis", "Sérasieh", "Grosaillieh",
                    "Vocah", "Coconoa", "Pahya", "Canel", "Jitato", "Alfine"}
        forbidden = {"Hestu", "Kass", "Purah", "Pikango", "Bolson", "Hudson",
                     "Cado", "Koko", "Paya", "Symin", "Jiahto", "Finley"}
        self.assertTrue(expected <= givers)
        self.assertTrue(expected <= facts)
        self.assertFalse(forbidden & givers)
        self.assertFalse(forbidden & facts)
        self.assertIn("Benjamin", givers)
        self.assertNotIn("Benjaminmin", givers)

    def test_corrective_step_six_audit_is_recursive_and_clean(self):
        audit = analyze({})["audit_nomenclature"]
        self.assertEqual(audit["schema_version"], 2)
        self.assertTrue(audit["champs_de_fiches_controles_recursivement"])
        self.assertEqual(audit["statut"], "complet")
        self.assertEqual(audit["anomalies"], [])

    def test_corrective_step_six_replaces_numbered_persistent_boss_names(self):
        report = analyze({})
        bosses = [item for category in ("hinox", "talus", "moldarquors")
                  for item in report["categories"][category]["elements"]]
        import re
        self.assertEqual(len(bosses), 84)
        self.assertFalse(any(re.search(r" \d+$", item["name"]) for item in bosses))
        self.assertTrue(all(" - près de " in item["name"] and item.get("nearby") for item in bosses))


if __name__ == "__main__":
    unittest.main()