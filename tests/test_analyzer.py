import unittest
from unittest.mock import patch

from botw_companion.analyzer import (SHRINE_CHESTS_REMAINING_FILTER,
                                     _official_map, analyze)
from botw_companion.resources import load_catalog, load_completion_standard


class AnalyzerTests(unittest.TestCase):
    def test_quest_completion_uses_journal_finish_flags(self):
        catalog = load_catalog()
        expected = {
            "findthefairyfountain": "FairyFountain_Finish",
            "destroyganon": "GanonQuest_Finished",
            "thegutcheckchallenge": "GoronCamp_Finish",
            "thetestofwood": "ShieldofKolog_Finish",
        }
        quests = {item["id"]: item for key in ("main_quests", "shrine_quests")
                  for item in catalog[key]}
        for name, flag in expected.items():
            self.assertEqual(quests[name]["rule"], [{"flag": flag, "value": True}])

    def test_evaluates_flags_without_confusing_false_and_missing(self):
        catalog = {
            "shrines": [{"flag": "a"}, {"flag": "b"}],
            "shrine_chests": [], "world_chests": [], "dungeon_chests": [],
            "main_quests": [{"name": "Q", "rule": [{"flag": "q1", "value": True}, {"flag": "q2", "value": True}]}],
            "shrine_quests": [], "side_quests": [], "memories": [],
            "compendium": [{"name": "Test", "flag": "IsRegisteredPictureBook_Test"}],
            "armor_owned": [], "koroks": [], "towers": [], "locations": [],
            "official_map_locations": [],
            "hinoxes": [], "taluses": [], "moldugas": [],
            "canonical": {
                "compendium": [1], "main_quests": [], "dlc_main_quests": [],
                "side_quests": [], "memories": [], "enhanceable_armor": [],
            },
        }
        with patch("botw_companion.analyzer.load_catalog", return_value=catalog):
            report = analyze({"a": True, "b": False, "q1": True, "q2": False,
                              "IsRegisteredPictureBook_Test": True})
        self.assertEqual(report["categories"]["sanctuaires"]["faits"], 1)
        self.assertEqual(len(report["categories"]["sanctuaires"]["restants"]), 1)
        self.assertEqual(report["categories"]["compendium"]["faits"], 1)
        self.assertEqual(report["categories"]["quetes_principales"]["faits"], 0)

    def test_armor_level_and_next_materials_come_from_inventory(self):
        armor = {
            "name": "Test Armor", "id": "Armor_001_Upper", "flag": "IsGet_Armor_001_Upper",
            "variants": [f"Armor_{number:03d}_Upper" for number in range(1, 6)],
            "recettes": {"4": [{"name": "Test Material", "id": "Item_Test", "quantity": 5}]},
        }
        catalog = {
            "shrines": [], "shrine_chests": [], "world_chests": [], "dungeon_chests": [],
            "main_quests": [], "shrine_quests": [], "side_quests": [], "memories": [],
            "compendium": [], "armor_owned": [armor], "koroks": [], "towers": [], "locations": [],
            "official_map_locations": [], "hinoxes": [], "taluses": [], "moldugas": [], "manual": {},
        }
        inventory = [{"id": "Armor_004_Upper", "quantite": 0}, {"id": "Item_Test", "quantite": 3}]
        with patch("botw_companion.analyzer.load_catalog", return_value=catalog):
            report = analyze({}, inventory)
        owned = report["categories"]["armures"]["elements"][0]
        maximal = report["categories"]["armures_max"]["elements"][0]
        self.assertEqual((owned["possede"], owned["niveau"], owned["etoiles"]), (True, 3, "★★★☆"))
        self.assertEqual(owned["prochaine_amelioration"]["materiaux"][0]["manque"], 2)
        self.assertEqual(report["categories"]["armures"]["faits"], 1)
        self.assertEqual(report["categories"]["armures_max"]["faits"], 0)
        self.assertEqual(maximal["statut"], "niveau 3/4")

    def test_official_map_catalog_has_exactly_187_markers(self):
        catalog = load_catalog()
        self.assertEqual(len(catalog["official_map_locations"]), 187)
        self.assertEqual(sum(x["type"] == "tour" for x in catalog["official_map_locations"]), 15)
        self.assertEqual(sum(x["type"] == "créature divine" for x in catalog["official_map_locations"]), 4)

    def test_official_map_base_and_dlc_formulas(self):
        catalog = load_catalog()
        flags = {item["flag"]: True for item in catalog["koroks"]}
        flags.update({item["flag"]: True for item in catalog["official_map_locations"]})
        flags.update({f"Location_Dungeon{i:03d}": True for i in range(120)})
        base = _official_map(catalog, flags)
        self.assertEqual((base["faits"], base["total"], base["pourcentage"]), (1207, 1207, 100.0))
        flags.update({f"Location_Dungeon{i:03d}": True for i in range(120, 137)})
        dlc = _official_map(catalog, flags)
        self.assertEqual((dlc["faits"], dlc["total"], dlc["pourcentage"]), (1224, 1224, 100.0))

    def test_all_quests_and_memories_have_structured_coordinates(self):
        catalog = load_catalog()
        groups = ("main_quests", "shrine_quests", "side_quests", "memories")
        items = [item for group in groups for item in catalog[group]]
        self.assertEqual(len(items), 175)
        self.assertTrue(all(item.get("x") is not None and item.get("z") is not None for item in items))
        self.assertTrue(all(item.get("geo_points") for item in items))
        self.assertEqual(sum(len(item["geo_points"]) for item in items), 252)

    def test_shrine_quest_start_and_destination_are_not_confused(self):
        catalog = load_catalog()
        quest = next(item for item in catalog["shrine_quests"]
                     if item["id"] == "thestolenheirloom")
        self.assertEqual((quest["x"], quest["z"]), (1781.0, 984.0))
        self.assertEqual([point["role"] for point in quest["geo_points"]],
                         ["depart", "destination"])
        destination = quest["geo_points"][1]
        self.assertEqual(destination["source_id"], "Dungeon112")
        self.assertAlmostEqual(destination["x"], 2039.633, places=3)

    def test_xenoblade_and_dlc_memories_are_geographically_complete(self):
        catalog = load_catalog()
        xenoblade = next(item for item in catalog["side_quests"]
                         if item["name"] == "[Xenoblade Chronicles 2]")
        self.assertEqual(len(xenoblade["geo_points"]), 3)
        self.assertEqual({point["source_id"] for point in xenoblade["geo_points"]},
                         {"E-7_Static", "I-1_Static", "C-2_Static"})
        dlc = [item for item in catalog["memories"] if item["dlc"]]
        self.assertEqual(len(dlc), 5)
        self.assertTrue(all(item["name"].startswith("EX ") for item in dlc))

    def test_every_catalog_item_has_an_individual_guide(self):
        report = analyze({})
        self.assertEqual(report["schema_version"], 17)
        self.assertEqual(report["synthese"]["total"], 3400)
        self.assertEqual(len(report["categories"]), 31)
        for category, data in report["categories"].items():
            with self.subTest(category=category):
                self.assertGreater(data["total"], 0)
                for item in data["elements"]:
                    guide = item.get("guide", {})
                    self.assertTrue(guide.get("personalized"), item.get("name"))
                    self.assertEqual(guide.get("category"), category)
                    self.assertTrue(guide.get("current_action"), item.get("name"))
                    self.assertTrue(guide.get("steps"), item.get("name"))
                    self.assertTrue(guide.get("completion", {}).get("condition"), item.get("name"))
                    self.assertNotIn("fiche universelle de secours", " ".join(guide.get("warnings", [])))

    def test_corrective_step_five_every_visible_item_has_a_quality_level(self):
        report = analyze({})
        visible = report["elements"] + report["map_layers"]
        self.assertEqual(len(visible), 8452)
        self.assertTrue(all(item["guide"]["version"] == 3 for item in visible))
        self.assertTrue(all(item["guide"]["detailed_steps"] for item in visible))
        self.assertTrue(all(item["guide"]["specificity_label"] for item in visible))
        self.assertTrue(all(item["guide"]["quality_level"] in {1, 2, 3} for item in visible))
        self.assertEqual(report["audit_guides"]["version_3"], 8452)
        self.assertEqual(report["audit_guides"]["avec_solution_detaillee"], 8452)

    def test_corrective_step_five_never_overstates_a_complete_solution(self):
        report = analyze({})
        self.assertEqual(report["audit_guides"]["solutions_completes_invalides"], [])
        self.assertGreater(report["audit_guides"]["solutions_completes_valides"], 0)
        for item in report["elements"] + report["map_layers"]:
            guide = item["guide"]
            if guide["quality_level"] == 3:
                self.assertGreaterEqual(len(guide["detailed_steps"]), 3)
                self.assertTrue(guide["sources"])
                self.assertTrue(guide["rewards"])

    def test_step_five_all_shrines_expose_each_physical_chest(self):
        report = analyze({})
        shrines = report["categories"]["sanctuaires"]["elements"]
        chest_objectives = report["categories"]["coffres_sanctuaires"]["elements"]
        self.assertEqual((len(shrines), len(chest_objectives)), (136, 136))
        self.assertEqual(sum(len(item["guide"].get("chest_details", [])) for item in shrines), 205)
        self.assertEqual(sum(len(item["guide"].get("chest_details", [])) for item in chest_objectives), 205)
        for item in shrines + chest_objectives:
            with self.subTest(shrine=item["name"]):
                guide = item["guide"]
                self.assertEqual(len(guide["chest_details"]), item["chest_count"])
                self.assertTrue(guide["interior_map"])
                self.assertTrue(all(chest["content"] and chest["interior_position"]["x"] is not None
                                    for chest in guide["chest_details"]))

    def test_corrective_step_five_links_every_quest_to_its_real_event_flow(self):
        report = analyze({})
        quests = [item for category in ("quetes_principales", "quetes_sanctuaires", "quetes_secondaires")
                  for item in report["categories"][category]["elements"]]
        self.assertEqual(len(quests), 152)
        self.assertTrue(all(item["guide"].get("quest_evidence", {}).get("event_flow_found")
                            for item in quests))
        self.assertEqual(sum(item["guide"].get("quest_evidence", {}).get("event_nodes", 0) > 0
                             for item in quests), 149)
        self.assertEqual(report["audit_solutions"]["quests_with_event_flow_file"], 152)
        self.assertEqual(report["audit_solutions"]["quests_with_nonempty_event_flow"], 149)

    def test_corrective_step_five_quests_expose_independent_editorial_facts(self):
        report = analyze({})
        quests = [item for category in ("quetes_principales", "quetes_sanctuaires", "quetes_secondaires")
                  for item in report["categories"][category]["elements"]]
        self.assertEqual(report["audit_solutions"]["quests_with_editorial_facts"], 152)
        self.assertEqual(report["audit_solutions"]["quests_with_named_giver"], 133)
        self.assertEqual(report["audit_solutions"]["quests_with_named_reward"], 140)
        self.assertEqual(sum(bool(item["guide"].get("quest_giver")) for item in quests), 133)
        self.assertEqual(sum("vérifier le dialogue final" not in " ".join(item["guide"]["rewards"])
                             for item in quests), 152)
        self.assertTrue(all(any(source.get("name", "").startswith("Zelda Wiki -")
                                for source in item["guide"]["sources"]) for item in quests))

    def test_alpha_19_every_quest_has_a_complete_specific_walkthrough(self):
        report = analyze({})
        quests = [item for category in ("quetes_principales", "quetes_sanctuaires", "quetes_secondaires")
                  for item in report["categories"][category]["elements"]]
        generic = ("lis l'objectif actuel", "suis les points ordonnés", "parle au donneur au point de départ")
        self.assertEqual(len(quests), 152)
        self.assertTrue(all(len(item.get("quest_walkthrough", {}).get("steps", [])) >= 3
                            for item in quests))
        self.assertTrue(all(item["guide"]["quality_level"] == 3 for item in quests))
        self.assertTrue(all(item["guide"]["specificity"] == "complete_quest_walkthrough"
                            for item in quests))
        self.assertFalse(any(marker in " ".join(item["guide"]["detailed_steps"]).lower()
                             for item in quests for marker in generic))
        self.assertTrue(all(any("Zelda Dungeon" in source.get("name", "")
                                for source in item["guide"]["sources"]) for item in quests))

    def test_alpha_19_started_quest_preserves_detected_progress_and_safe_resume(self):
        report = analyze({"PictureMemory_Activated": True, "PictureMemory_GetShirt": True})
        quest = next(item for item in report["categories"]["quetes_principales"]["elements"]
                     if item["quest_internal_id"] == "PictureMemory")
        steps = quest["guide"]["steps"]
        self.assertTrue(quest["commence"])
        self.assertTrue(any(step["title"] == "Progression interne détectée" for step in steps))
        self.assertTrue(any(step["title"] == "Reprendre la solution détaillée"
                            and step["state"] == "actuel" for step in steps))
        self.assertEqual(sum(step["title"].startswith("Solution ") for step in steps), 3)

    def test_step_five_no_quest_keeps_a_generic_reward(self):
        report = analyze({})
        quests = [item for category in ("quetes_principales", "quetes_sanctuaires", "quetes_secondaires")
                  for item in report["categories"][category]["elements"]]
        self.assertEqual(len(quests), 152)
        self.assertTrue(all(item["guide"]["rewards"] for item in quests))
        self.assertFalse(any("récompense de quête" in " ".join(item["guide"]["rewards"]).lower()
                             for item in quests))

    def test_step_five_quest_stage_labels_are_never_the_old_placeholders(self):
        catalog = load_catalog()
        stages = [stage for group in ("main_quests", "shrine_quests", "side_quests")
                  for item in catalog[group] for stage in item.get("quest_stage_flags", [])]
        self.assertEqual(len(stages), 242)
        self.assertFalse(any(stage["label"].startswith("Étape de progression") for stage in stages))
        self.assertGreaterEqual(sum(not stage["label"].startswith("Progression interne") for stage in stages), 74)

    def test_corrective_step_five_documents_all_trial_rooms(self):
        report = analyze({})
        trials = report["categories"]["epreuves_epee"]["elements"]
        rooms = [room for item in trials for room in item["guide"]["trial_rooms"]]
        self.assertEqual([len(item["guide"]["trial_rooms"]) for item in trials], [13, 17, 24])
        self.assertEqual(len(rooms), 54)
        self.assertEqual(sum(room["kind"] == "combat" for room in rooms), 45)
        self.assertEqual(sum(room["kind"] == "rest" for room in rooms), 6)
        self.assertEqual(sum(room["kind"] == "reward" for room in rooms), 3)
        self.assertTrue(all(room["enemies"] and room["strategy"] and room["source"] for room in rooms))
        self.assertTrue(all(item["guide"]["quality_level"] == 3 for item in trials))

    def test_step_six_shrines_quests_koroks_and_bosses_are_specialized(self):
        report = analyze({})
        shrines = report["categories"]["sanctuaires"]["elements"]
        quests = [item for category in ("quetes_principales", "quetes_sanctuaires", "quetes_secondaires")
                  for item in report["categories"][category]["elements"]]
        koroks = report["categories"]["korogus"]["elements"]
        bosses = report["categories"]["bosses_scenarises"]["elements"]
        self.assertEqual((len(shrines), len(quests), len(koroks), len(bosses)), (136, 152, 900, 13))
        self.assertTrue(all(item["guide"].get("mechanic") for item in shrines))
        self.assertFalse(any(item["guide"]["mechanic"].startswith("Épreuve nommée") for item in shrines))
        self.assertTrue(all(len(item["guide"]["detailed_steps"]) >= 3 for item in quests))
        self.assertTrue(all(item["guide"]["specificity"] == "verified_korok_puzzle" for item in koroks))
        self.assertTrue(all(item["guide"]["quality_level"] == 3 for item in koroks))
        self.assertTrue(all(item["guide"]["mechanic"] for item in koroks))
        self.assertFalse(any("pas contenu" in " ".join(item["guide"]["warnings"]) for item in koroks))
        self.assertTrue(all(item["guide"]["specificity"] == "scripted_boss_complete" for item in bosses))

    def test_step_five_all_scripted_bosses_have_complete_verified_guides(self):
        report = analyze({})
        bosses = report["categories"]["bosses_scenarises"]["elements"]
        self.assertEqual(len(bosses), 13)
        for boss in bosses:
            with self.subTest(boss=boss["name"]):
                guide = boss["guide"]
                self.assertEqual(guide["quality_level"], 3)
                self.assertGreaterEqual(len(guide["detailed_steps"]), 3)
                self.assertTrue(guide["prerequisites"])
                self.assertTrue(guide["rewards"])
                self.assertTrue(guide["respawn_condition"])
                self.assertTrue(guide["sources"])
                self.assertNotIn("Butin du combat", guide["rewards"])

    def test_step_six_farm_guides_keep_the_blood_moon_warning(self):
        report = analyze({})
        farm = [item for item in report["map_layers"] if item.get("farm")]
        self.assertEqual(len(farm), 4489)
        self.assertTrue(all("lune de sang" in " ".join(item["guide"]["warnings"]).lower()
                            for item in farm))
        self.assertEqual(report["audit_guides"]["points_farm_avec_avertissement_lune_de_sang"],
                         len(farm))

    def test_every_located_item_has_uniform_map_points(self):
        report = analyze({})
        located = [item for item in report["elements"]
                   if item.get("x") is not None and item.get("z") is not None]
        self.assertTrue(located)
        self.assertTrue(all(item.get("geo_points") for item in located))
        for item in located:
            self.assertTrue(all(point.get("x") is not None and point.get("z") is not None
                                for point in item["geo_points"]))

    def test_all_quests_have_discovery_and_intermediate_progress_metadata(self):
        catalog = load_catalog()
        quests = [item for group in ("main_quests", "shrine_quests", "side_quests")
                  for item in catalog[group]]
        self.assertEqual(len(quests), 152)
        self.assertTrue(all(item.get("started_rule") for item in quests))
        self.assertTrue(all(item.get("quest_internal_id") for item in quests))
        self.assertEqual(sum(len(item.get("quest_stage_flags", [])) for item in quests), 242)

    def test_all_known_dlc_items_receive_guides(self):
        report = analyze({})
        dlc_items = [item for item in report["elements"] if item.get("dlc")]
        self.assertGreaterEqual(len(dlc_items), 100)
        self.assertTrue(all(item["guide"]["personalized"] for item in dlc_items))

    def test_champions_ballad_main_quests_are_dlc(self):
        catalog = load_catalog()
        dlc = {item["id"] for item in catalog["main_quests"] if item.get("dlc")}
        self.assertEqual(dlc, {
            "championdarukssong", "championmiphassong", "championrevalissong",
            "championurbosassong", "thechampionsballad",
        })

    def test_only_final_trial_dungeon_chests_are_dlc(self):
        catalog = load_catalog()
        dlc = [item for item in catalog["dungeon_chests"] if item.get("dlc")]
        base = [item for item in catalog["dungeon_chests"] if not item.get("dlc")]
        self.assertEqual((len(dlc), len(base)), (7, 35))
        self.assertTrue(all(item["secteur"] == "Épreuve finale de l'Épée" for item in dlc))

    def test_trial_chests_have_a_filterable_region(self):
        catalog = load_catalog()
        trials = [item for item in catalog["world_chests"]
                  if item.get("id", "").startswith("AocField-")]
        self.assertEqual(len(trials), 49)
        self.assertTrue(all(item.get("region") == "Épreuves de l'épée" for item in trials))

    def test_step_seven_uses_exact_french_enemy_variants(self):
        report = analyze({})
        layers = report["map_layers"]
        expected = {
            "Enemy_Bokoblin_Bone_Junior": "Stalbokoblin",
            "Enemy_Octarock_Desert": "Octocoffre",
            "Enemy_Wizzrobe_Electric_Senior": "Sorcier fulguro",
            "Enemy_Golem_Little_Ice": "Givrok",
            "RemainsFire_Drone_A_01": "Héliss",
        }
        for actor, subtype in expected.items():
            item = next(x for x in layers if x.get("acteur") == actor)
            self.assertEqual(item["subtype"], subtype)
            self.assertTrue(item["name"].startswith(subtype))
            self.assertTrue(item["repeatable"])
            self.assertTrue(item["farm"])

    def test_step_seven_nomenclature_audit_is_clean(self):
        report = analyze({})
        audit = report["audit_nomenclature"]
        self.assertEqual(audit["statut"], "complet")
        self.assertEqual(audit["elements_visibles_controles"], 8452)
        self.assertGreater(audit["points_ennemis_controles"], 3000)
        self.assertEqual(audit["anomalies"], [])

    def test_step_seven_official_dlc_and_service_names(self):
        report = analyze({})
        trials = report["categories"]["epreuves_epee"]["elements"]
        self.assertEqual([x["name"] for x in trials], [
            "Épreuves basiques de l'épée",
            "Épreuves moyennes de l'épée",
            "Épreuves finales de l'épée",
        ])
        self.assertEqual(report["categories"]["malanya"]["label"], "Marlon")
        self.assertEqual(trials[0]["content_origin_label"], "DLC 1 - Les épreuves légendaires")
        self.assertTrue(all(item["x"] == 431.66 and item["z"] == -2110.99 for item in trials))
        self.assertTrue(all(item["location_role"] == "entrée de l'activité" for item in trials))
        self.assertTrue(all(item["content_origin"] == "master_trials" for item in trials))

    def test_public_locations_include_three_official_markers(self):
        catalog = load_catalog()
        self.assertEqual(len(catalog["locations"]), 168)
        flags = {item["flag"] for item in catalog["locations"]}
        self.assertTrue({
            "Location_AncientLabo", "Location_HatenoLabo", "Location_StartPoint",
        }.issubset(flags))

    def test_companion_score_is_named_as_automatic_coverage(self):
        self.assertEqual(analyze({})["synthese"]["libelle"], "Indice de couverture automatique")

    def test_completion_standard_is_explicit_and_fully_derived(self):
        reference = analyze({})["referentiel_100"]
        self.assertEqual(reference["schema_version"], 3)
        self.assertEqual(len(reference["axes"]), 8)
        self.assertGreaterEqual(len(reference["categories"]), 40)
        self.assertTrue(reference["global_score"]["available"])
        self.assertEqual(reference["audit"]["obligatoires_incompletes"], 0)
        self.assertTrue(all("current_status" not in item for item in load_completion_standard()["categories"]))

    def test_completion_standard_matches_official_map_formula(self):
        official = analyze({})["referentiel_100"]["official_map"]
        self.assertEqual(official["base"]["total"], 1207)
        self.assertEqual(official["dlc"]["total"], 1224)
        self.assertEqual(
            official["base"]["korogus"] + official["base"]["sanctuaires"] + official["base"]["marqueurs"],
            official["base"]["total"],
        )
        self.assertEqual(
            official["dlc"]["korogus"] + official["dlc"]["sanctuaires"] + official["dlc"]["marqueurs"] + official["dlc"]["donjon_final"],
            official["dlc"]["total"],
        )

    def test_repeatable_activities_never_block_the_main_score(self):
        categories = analyze({})["referentiel_100"]["categories"]
        unbounded = [item for item in categories if item["repeatable"] and not item["finite"]]
        self.assertTrue(unbounded)
        self.assertTrue(all(item["inclusion"] == "informational" for item in unbounded))

    def test_every_current_report_category_is_represented_in_standard(self):
        report = analyze({})
        represented = {item.get("report_category") for item in report["referentiel_100"]["categories"]}
        represented.update(
            category
            for item in report["referentiel_100"]["categories"]
            for category in item.get("report_categories", [])
        )
        self.assertTrue(set(report["categories"]).issubset(represented))

    def test_step_three_map_layers_are_informational_and_complete(self):
        report = analyze({})
        layers = report["map_layers"]
        self.assertEqual(len(layers), 4802)
        self.assertEqual(sum(item["layer_type"] == "enemy_lynel" for item in layers), 23)
        self.assertEqual(sum(item["layer_type"] == "enemy_guardian" for item in layers), 154)
        self.assertEqual(sum(item["layer_type"] == "enemy_guardian_scout" for item in layers), 21)
        self.assertEqual(sum(item["layer_type"] == "enemy_hinox" for item in layers), 40)
        self.assertEqual(sum(item["layer_type"] == "enemy_talus" for item in layers), 41)
        self.assertEqual(sum(item["layer_type"] == "enemy_molduga" for item in layers), 5)
        self.assertTrue(all(item["informational"] for item in layers))
        repeatable = [item for item in layers if item["layer_type"].startswith("enemy_")]
        self.assertTrue(all(item["repeatable"] for item in repeatable))
        self.assertTrue(all(item["filter_group"] == "monstres" for item in repeatable))

    def test_farm_layers_ignore_permanent_defeat_flags(self):
        flags = {
            "MamonoShop_BigEnemy_Giant_Finish": True,
            "MamonoShop_BigEnemy_Golem_Finish": True,
            "MamonoShop_BigEnemy_Sandworm_Finish": True,
        }
        report = analyze(flags)
        farm = [item for item in report["map_layers"] if item.get("farm")]
        self.assertEqual(len(farm), 4489)
        self.assertTrue(all(not item["termine"] for item in farm))
        self.assertTrue(all(item["statut"] == "réapparaît après une lune de sang" for item in farm))

    def test_every_visible_item_has_a_unique_stable_tracking_id(self):
        before = analyze({})
        after = analyze({"Clear_Dungeon000": True})
        before_ids = [item["tracking_id"] for item in before["elements"] + before["map_layers"]]
        after_ids = [item["tracking_id"] for item in after["elements"] + after["map_layers"]]
        self.assertEqual(len(before_ids), 8452)
        self.assertEqual(len(before_ids), len(set(before_ids)))
        self.assertEqual(before_ids, after_ids)

    def test_step_three_filter_taxonomy_is_hierarchical(self):
        groups = analyze({})["filter_groups"]
        self.assertEqual(len(groups), 10)
        types = {item["id"] for group in groups for item in group["types"]}
        self.assertTrue({
            "sanctuaires", "quetes_principales", "coffre_arme_une_main",
            "coffre_gros_rubis", "equipements_particuliers", "lynels", "gardiens",
            "grandes_fees", "marmites", "statues_deesse", "radeaux",
            "bokoblins", "moblins", "lezalfos", "hinox_farm",
            "objectifs_quete", "nano_gardiens", "auberges", "boutiques_armures",
            "bonus_expansion", "ameliorations_prodiges", "fonctionnalites_dlc",
            "tresors_chiens",
        }.issubset(types))

    def test_completed_shrine_with_missing_chest_has_a_dedicated_filter(self):
        chest = load_catalog()["shrine_chests"][0]
        report = analyze({f"Clear_{chest['id']}": True})
        objective = next(
            item for item in report["categories"]["coffres_sanctuaires"]["elements"]
            if item["id"] == chest["id"]
        )
        self.assertFalse(objective["termine"])
        self.assertTrue(objective["sanctuaire_termine"])
        self.assertIn(SHRINE_CHESTS_REMAINING_FILTER,
                      objective["content_filter_types"])
        special = next(
            item for group in report["filter_groups"] for item in group["types"]
            if item["id"] == SHRINE_CHESTS_REMAINING_FILTER
        )
        self.assertEqual(special["label"], "Sanctuaires terminés - coffres restants")
        self.assertEqual(special["count"], 1)

    def test_corrective_step_three_filter_counts_match_an_independent_reference(self):
        report = analyze({})
        audit = report["filter_scope_audit"]
        types = [item for group in report["filter_groups"] for item in group["types"]]
        self.assertEqual(audit["status"], "complete")
        self.assertEqual(audit["counts"]["filter_types"], 74)
        self.assertTrue(all(item["expected_count"] is not None for item in types))
        self.assertTrue(all(item["count_matches_reference"] for item in types))
        self.assertEqual(sum(item["count"] for item in types), 8452)

    def test_corrective_step_three_normal_mode_hides_every_expert_only_placement(self):
        normal = analyze({}, save_context={"mode": "normal"})["filter_scope_audit"]
        expert = analyze({}, save_context={"mode": "expert"})["filter_scope_audit"]
        self.assertEqual(normal["default_mode_filter"], "normal")
        self.assertEqual(expert["default_mode_filter"], "expert")
        self.assertEqual(normal["counts"]["expert_only"], 755)
        self.assertEqual(normal["counts"]["default_visible"], 8452 - 755)
        self.assertEqual(expert["counts"]["default_visible"], 8452)

    def test_corrective_step_three_audits_all_expert_enemy_families(self):
        monsters = {item["id"]: item for item in analyze({})["filter_scope_audit"]["monster_types"]}
        self.assertEqual(len(monsters), 17)
        self.assertEqual({key: monsters[key]["expert_only_count"] for key in (
            "bokoblins", "lezalfos", "moblins", "sorciers", "lynels", "octos_aeriens"
        )}, {
            "bokoblins": 95, "lezalfos": 50, "moblins": 5,
            "sorciers": 3, "lynels": 1, "octos_aeriens": 600,
        })
        self.assertEqual(sum(item["expert_only_count"] for item in monsters.values()), 754)

    def test_corrective_step_three_yigas_are_a_fixed_non_exhaustive_subset(self):
        report = analyze({})
        yigas = [item for item in report["map_layers"] if item["layer_type"] == "enemy_yiga"]
        self.assertEqual(len(yigas), 20)
        self.assertTrue(all(item["placement_kind"] == "fixed_confirmed" for item in yigas))
        self.assertTrue(all(item["coverage_scope"] == "confirmed_subset" for item in yigas))
        self.assertTrue(all("AutoPlacementMgr" in item["coverage_note"] for item in yigas))
        limitation = report["filter_scope_audit"]["dynamic_limitations"][0]
        self.assertEqual((limitation["id"], limitation["mapped_count"]), ("yigas_dynamiques", 0))

    def test_corrective_step_three_separates_farm_from_permanent_victories(self):
        report = analyze({"MainField_Enemy_Giant_123": True})
        farm = [item for item in report["map_layers"] if item.get("farm")]
        permanent = [item for item in report["elements"]
                     if item["categorie"] in {"hinox", "talus", "moldarquors"}]
        self.assertEqual(len(farm), 4489)
        self.assertTrue(all(item["activity_scope"] == "repeatable_farm" for item in farm))
        self.assertEqual(len(permanent), 84)
        self.assertTrue(all(item["activity_scope"] == "permanent_victory" for item in permanent))
        self.assertTrue(all(not item["termine"] for item in farm))

    def test_corrective_step_three_distinguishes_map_list_and_missing_coordinates(self):
        report = analyze({})
        items = report["elements"] + report["map_layers"]
        self.assertTrue(all(item["display_scope"] in {"map_and_list", "interior_only", "list_only"} for item in items))
        compendium = report["categories"]["compendium"]["elements"]
        self.assertTrue(all(item["location_status"] == "no_natural_location" for item in compendium))
        missing = [item for item in items if item["location_status"] == "coordinates_missing"]
        self.assertEqual(len(missing), report["filter_scope_audit"]["counts"]["coordinates_missing"])
        self.assertEqual(missing, [])

    def test_corrective_step_four_references_every_physical_interior_chest(self):
        report = analyze({})
        audit = report["audit_cartographie"]
        self.assertEqual(audit["shrine_completion_entries"], 136)
        self.assertEqual(audit["physical_shrine_chests"], 205)
        self.assertEqual(audit["trial_chests"], 49)
        self.assertEqual(audit["dungeon_chests"], 42)
        self.assertEqual(audit["status"], "complete")
        self.assertEqual(audit["invalid_world_coordinates"], [])
        self.assertEqual(audit["invalid_interior_coordinates"], [])
        self.assertEqual(audit["duplicate_stable_identities"], [])
        shrines = report["categories"]["coffres_sanctuaires"]["elements"]
        self.assertEqual(sum(item["chest_count"] for item in shrines), 205)
        self.assertTrue(all(item["interior_chests"] for item in shrines))
        self.assertTrue(all(chest["content"] for item in shrines for chest in item["interior_chests"]))
        self.assertTrue(all(item["filter_type"] != "coffre_autre" for item in shrines))

    def test_corrective_step_four_keeps_interior_coordinates_off_hyrule(self):
        report = analyze({})
        trial = [item for item in report["categories"]["coffres_monde"]["elements"]
                 if item.get("map_context") == "trial_interior"]
        dungeon = report["categories"]["coffres_donjons"]["elements"]
        self.assertEqual((len(trial), len(dungeon)), (49, 42))
        self.assertTrue(all(item["display_scope"] == "interior_only" for item in trial + dungeon))
        self.assertTrue(all(item["location_status"] == "interior_coordinates" for item in trial + dungeon))
        self.assertTrue(all("x" not in item and "z" not in item for item in trial + dungeon))
        self.assertTrue(all(item["interior_position"]["content"] for item in trial + dungeon))

    def test_corrective_step_four_has_no_unexplained_coordinate_gap(self):
        report = analyze({})
        audit = report["filter_scope_audit"]["counts"]
        self.assertEqual(audit["coordinates_missing"], 0)
        self.assertEqual(audit["interior_only"], 91)
        self.assertEqual(audit["map_and_list"] + audit["interior_only"] + audit["list_only"], 8452)

    def test_corrective_step_four_replaces_generic_service_names(self):
        services = {"statue_deesse", "marmite", "radeau", "kilton", "auberge",
                    "boutique_armures", "magasin_general", "bijouterie"}
        layers = [item for item in analyze({})["map_layers"] if item["layer_type"] in services]
        self.assertTrue(all(" - " in item["name"] for item in layers))
        self.assertTrue(all(item.get("nearby") for item in layers))
        self.assertTrue(all(item.get("nearby_distance_m") is not None for item in layers))

    def test_all_dog_treasures_are_localized_and_manual_only(self):
        report = analyze({})
        dogs = report["categories"]["tresors_chiens"]
        self.assertEqual(dogs["total"], 15)
        self.assertTrue(dogs["score_excluded"])
        self.assertTrue(all(item["manual_only"] for item in dogs["elements"]))
        self.assertTrue(all(item.get("x") is not None and item.get("z") is not None
                            for item in dogs["elements"]))
        self.assertTrue(all(not item["guide"]["completion"]["automatic"]
                            for item in dogs["elements"]))

    def test_step_three_permanent_categories_do_not_double_count_views(self):
        report = analyze({})
        expected = {
            "equipements_particuliers": 40,
            "epreuves_epee": 3,
            "medailles_kilton": 3,
            "recompenses_uniques": 2,
            "objets_speciaux": 2,
            "harnachements": 12,
            "creatures_divines": 4,
            "bosses_scenarises": 13,
            "bonus_expansion": 3,
            "ameliorations_prodiges": 4,
            "fonctionnalites_dlc": 2,
        }
        for category, total in expected.items():
            self.assertEqual(report["categories"][category]["total"], total)
        self.assertTrue(report["categories"]["creatures_divines"]["score_excluded"])
        self.assertTrue(report["categories"]["bosses_scenarises"]["score_excluded"])
        self.assertEqual(
            sum(category["total"] for category in report["categories"].values())
            - report["synthese"]["total"],
            250,
        )

    def test_main_profile_excludes_amiibo_and_master_mode(self):
        report = analyze({})
        profiles = {item["id"]: item["progress"] for item in report["referentiel_100"]["profiles"]}
        self.assertEqual(profiles["automatique"]["total"], 3400)
        self.assertEqual(profiles["amiibo"]["total"], 44)
        self.assertEqual(profiles["base"]["total_manuel"], 15)
        self.assertEqual(profiles["base"]["total"], 3415)
        self.assertEqual(profiles["dlc"]["total"], 3580)

    def test_automatic_profile_switches_to_dlc_only_with_save_evidence(self):
        base = analyze({})["referentiel_100"]
        dlc = analyze({"BalladOfHeroes_Activated": True})["referentiel_100"]
        base_profiles = {item["id"]: item for item in base["profiles"]}
        dlc_profiles = {item["id"]: item for item in dlc["profiles"]}
        self.assertEqual(base["selection"]["detected_content_profile"], "base")
        self.assertEqual(dlc["selection"]["detected_content_profile"], "dlc")
        self.assertEqual(base_profiles["automatique"]["progress"]["total"], 3400)
        self.assertEqual(dlc_profiles["automatique"]["progress"]["total"], 3565)
        self.assertEqual(base_profiles["base"]["progress"]["total"], 3415)
        self.assertEqual(dlc_profiles["dlc"]["progress"]["total"], 3580)

    def test_expert_profile_is_separate_and_requires_expert_context(self):
        normal = analyze({})["referentiel_100"]
        expert = analyze({}, save_context={"mode": "expert", "is_expert": True,
                                            "slot_number": 6, "detection": "fixture slot 6"})["referentiel_100"]
        normal_profiles = {item["id"]: item for item in normal["profiles"]}
        expert_profiles = {item["id"]: item for item in expert["profiles"]}
        self.assertFalse(normal_profiles["expert"]["available"])
        self.assertTrue(expert_profiles["expert"]["available"])
        self.assertEqual(expert["selection"]["save_mode"], "expert")
        self.assertEqual(expert["selection"]["selected_profile"], "expert")
        self.assertEqual(expert_profiles["expert"]["progress"]["total"], 3415)

    def test_expert_flag_is_used_when_slot_context_is_unavailable(self):
        reference = analyze({"IsLastPlayHardMode": True})["referentiel_100"]
        self.assertEqual(reference["selection"]["save_mode"], "expert")
        self.assertEqual(reference["selection"]["detection"], "flag IsLastPlayHardMode")

    def test_horse_gear_is_complete_automatic_and_origin_aware(self):
        gear = analyze({})["categories"]["harnachements"]["elements"]
        self.assertEqual(len(gear), 12)
        self.assertTrue(all(item.get("flag") for item in gear))
        self.assertEqual(sum(item["content_origin"] == "amiibo" for item in gear), 2)
        self.assertEqual(sum(item["content_origin"] == "champions_ballad" for item in gear), 2)

    def test_four_great_fairy_locations_use_one_truthful_save_counter(self):
        fairies = analyze({"FairyRevivalNum": 2})["categories"]["grandes_fees"]
        self.assertEqual(fairies["total"], 1)
        self.assertEqual(fairies["elements"][0]["progression"], 2)
        self.assertEqual(len(fairies["elements"][0]["geo_points"]), 4)
        self.assertFalse(fairies["elements"][0]["termine"])

    def test_official_map_exposes_both_override_scenarios(self):
        official = analyze({})["carte_officielle"]
        self.assertEqual(official["selected_mode"], "base")
        self.assertEqual(official["override_modes"], ["automatique", "base", "dlc"])
        self.assertEqual(official["scenarios"]["base"]["total"], 1207)
        self.assertEqual(official["scenarios"]["dlc"]["total"], 1224)

    def test_official_dlc_matrix_is_fully_implemented(self):
        audit = analyze({})["audit_dlc"]
        self.assertEqual(audit["status"], "complete")
        self.assertEqual(len(audit["families"]), 14)
        self.assertTrue(all(item["implemented"] == item["expected"]
                            for item in audit["families"]))

    def test_all_24_expansion_pass_world_chests_have_the_right_pack(self):
        catalog = load_catalog()
        chests = [item for item in catalog["world_chests"]
                  if "NoReaction_Aoc" in item.get("acteur", "")]
        self.assertEqual(len(chests), 24)
        by_origin = {origin: sum(item["content_origin"] == origin for item in chests)
                     for origin in {item["content_origin"] for item in chests}}
        self.assertEqual(by_origin, {
            "expansion_bonus": 3, "master_trials": 10, "champions_ballad": 11,
        })
        self.assertTrue(all(item["dlc"] for item in chests))
        self.assertTrue(all(item.get("region") for item in chests))

    def test_dlc_armor_is_split_bonus_pack_one_pack_two_and_free_update(self):
        armor = load_catalog()["special_armor"]
        counts = {origin: sum(item["content_origin"] == origin for item in armor)
                  for origin in {item["content_origin"] for item in armor}}
        self.assertEqual(counts["expansion_bonus"], 1)
        self.assertEqual(counts["master_trials"], 9)
        self.assertEqual(counts["champions_ballad"], 9)
        self.assertEqual(counts["free_update"], 3)
        xenoblade = next(item for item in load_catalog()["side_quests"]
                         if item["id"] == "xenobladechronicles2")
        self.assertFalse(xenoblade["dlc"])
        self.assertEqual(xenoblade["content_origin"], "free_update")

    def test_dlc_bosses_accept_equivalent_story_and_world_flags(self):
        report = analyze({
            "BalladOfHeroGerudo_FirstKillSandwormR": True,
            "BalladOfHeroGoron_FirstKillGolemR": True,
        })["categories"]["bosses_scenarises"]
        by_id = {item["id"]: item for item in report["elements"]}
        self.assertTrue(by_id["arquor-rex"]["termine"])
        self.assertTrue(by_id["mega-magrok"]["termine"])

    def test_dlc_features_and_champion_rewards_are_detected(self):
        report = analyze({
            "AoCVerAtLastPlay": 768,
            "AoC_HardMode_Enabled": True,
            "IsGet_Obj_DLC_HeroSoul_Zora": True,
            "IsGet_Obj_DLC_HeroSoul_Goron": True,
            "IsGet_Obj_DLC_HeroSoul_Rito": True,
            "IsGet_Obj_DLC_HeroSoul_Gerudo": True,
        })
        self.assertEqual(report["categories"]["fonctionnalites_dlc"]["faits"], 2)
        self.assertEqual(report["categories"]["ameliorations_prodiges"]["faits"], 4)
        trials = report["categories"]["epreuves_epee"]["elements"]
        self.assertEqual([item["master_sword_power"] for item in trials], [40, 50, 60])

    def test_special_equipment_accepts_upgrade_variants(self):
        report = analyze({}, [{"id": "Armor_199_Head", "quantite": 1}])
        divine_helm = next(item for item in report["categories"]["equipements_particuliers"]["elements"]
                           if item["id"] == "Armor_168_Head")
        self.assertTrue(divine_helm["termine"])

    def test_counter_and_permanent_reward_flags_are_evaluated(self):
        report = analyze({
            "FairyRevivalNum": 4,
            "100enemy_Clear_Junior": True,
            "MamonoShop_BigEnemy_Giant_Finish": True,
            "HatenoMini_CameraBoy_GetReward": True,
            "IsGet_Obj_WarpDLC": True,
        })
        self.assertEqual(report["categories"]["grandes_fees"]["faits"], 1)
        self.assertEqual(report["categories"]["epreuves_epee"]["faits"], 1)
        self.assertEqual(report["categories"]["medailles_kilton"]["faits"], 1)
        self.assertEqual(report["categories"]["recompenses_uniques"]["faits"], 1)
        self.assertEqual(report["categories"]["objets_speciaux"]["faits"], 1)


if __name__ == "__main__":
    unittest.main()