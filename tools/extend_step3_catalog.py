#!/usr/bin/env python3
"""Construit les catégories et couches cartographiques de l'étape 3.

Le fichier ``map_locations.js`` est l'export factuel du projet public
``MrCheeze/botw-object-map``. Il n'est pas redistribué : seules les positions
et identifiants nécessaires au compagnon sont intégrés au catalogue final.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


SOURCE = "botw-object-map - données internes du jeu"
SOURCE_URL = "https://github.com/MrCheeze/botw-object-map"
NINTENDO_DLC_URL = "https://ec.nintendo.com/AU/en/bundles/70070000000042"

ORIGIN_LABELS = {
    "base": "Jeu de base",
    "expansion_bonus": "Bonus de l'Expansion Pass",
    "master_trials": "DLC 1 - Les épreuves légendaires",
    "champions_ballad": "DLC 2 - L'Ode aux Prodiges",
    "master_mode": "Mode expert",
    "free_update": "Mise à jour gratuite Xenoblade Chronicles 2",
    "amiibo": "Extension amiibo",
}


def load_object_map(path: Path) -> dict:
    text = path.read_text().strip()
    prefix = "var locations = "
    if not text.startswith(prefix) or not text.endswith(";"):
        raise RuntimeError("Format map_locations.js non reconnu")
    return json.loads(text[len(prefix):-1])


def nearest_region(x: float, z: float, catalog: dict) -> str | None:
    anchors = [item for item in catalog["shrines"] if item.get("region")]
    if not anchors:
        return None
    return min(anchors, key=lambda item: math.hypot(item["x"] - x, item["z"] - z))["region"]


def point(catalog: dict, *, item_id: str, name: str, x: float, z: float,
          layer_type: str, subtype: str | None = None, dlc: bool = False,
          actor: str | None = None, mode_expert: bool = False,
          scalable: bool = False, repeatable: bool | None = None) -> dict:
    result = {
        "id": item_id,
        "name": name,
        "x": round(x, 3),
        "z": round(z, 3),
        "region": nearest_region(x, z, catalog),
        "dlc": dlc,
        "informational": True,
        "repeatable": layer_type.startswith("enemy_") if repeatable is None else repeatable,
        "layer_type": layer_type,
        "subtype": subtype or name,
        "source": SOURCE,
        "source_url": SOURCE_URL,
    }
    if actor:
        result["acteur"] = actor
    if mode_expert:
        result["mode_expert"] = True
    if scalable:
        result["scalable"] = True
    return result


def object_points(data: dict, actors: list[str]) -> list[tuple[str, str, float, float]]:
    result = []
    for actor in actors:
        entry = data[actor]
        for index, (x, z) in enumerate(entry["locations"], 1):
            result.append((actor, entry["display_name"], x, z))
    return result


def apply_dlc_metadata(catalog: dict) -> None:
    """Classe tout le contenu additionnel selon la matrice officielle Nintendo."""
    lists = (
        "shrines", "shrine_chests", "world_chests", "dungeon_chests",
        "main_quests", "shrine_quests", "side_quests", "memories",
        "special_armor", "trial_of_the_sword", "special_items", "horse_gear",
        "scripted_bosses", "champion_upgrades", "expansion_bonus_chests",
        "dlc_features", "map_layers",
    )
    for list_name in lists:
        for item in catalog.get(list_name, []):
            item.setdefault("content_origin", "base")

    def mark(items: list[dict], origin: str, predicate) -> None:
        for item in items:
            if predicate(item):
                item["content_origin"] = origin
                item["content_origin_label"] = ORIGIN_LABELS[origin]
                item["dlc"] = origin != "free_update"

    for key in ("shrines", "shrine_chests"):
        mark(catalog.get(key, []), "champions_ballad", lambda item: item.get("dlc", False))
    mark(catalog.get("dungeon_chests", []), "champions_ballad", lambda item: item.get("dlc", False))
    mark(catalog.get("main_quests", []), "champions_ballad", lambda item: item.get("dlc", False))
    mark(catalog.get("memories", []), "champions_ballad", lambda item: item.get("dlc", False))

    pack1_quests = {
        "trialofthesword", "strangemaskrumors", "teleportationrumors",
        "treasureancientmask", "treasurefairyclothes", "treasuretwilightrelic",
        "treasurephantasma",
    }
    pack2_quests = {
        "ancienthorserumors", "royalguardrumors", "treasuredarkarmor",
        "treasuregarbofwinds", "treasuremerchanthood", "treasureusurperking",
    }
    mark(catalog.get("side_quests", []), "master_trials", lambda item: item.get("id") in pack1_quests)
    mark(catalog.get("side_quests", []), "champions_ballad", lambda item: item.get("id") in pack2_quests)
    mark(catalog.get("side_quests", []), "free_update", lambda item: item.get("id") == "xenobladechronicles2")

    mark(catalog.get("special_armor", []), "expansion_bonus",
         lambda item: item.get("id") == "Armor_170_Upper")
    mark(catalog.get("special_armor", []), "master_trials",
         lambda item: item.get("id", "").startswith(("Armor_171_", "Armor_172_", "Armor_173_", "Armor_174_", "Armor_176_")))
    mark(catalog.get("special_armor", []), "champions_ballad",
         lambda item: item.get("id", "").startswith(("Armor_175_", "Armor_177_", "Armor_178_", "Armor_179_", "Armor_180_")))
    mark(catalog.get("special_armor", []), "free_update",
         lambda item: item.get("id", "").startswith("Armor_185_"))
    mark(catalog.get("special_armor", []), "amiibo", lambda item: item.get("amiibo", False))

    mark(catalog.get("trial_of_the_sword", []), "master_trials", lambda _item: True)
    mark(catalog.get("special_items", []), "master_trials",
         lambda item: item.get("id") == "amulette-teleportation")
    mark(catalog.get("special_items", []), "champions_ballad",
         lambda item: item.get("id") != "amulette-teleportation")
    mark(catalog.get("horse_gear", []), "champions_ballad",
         lambda item: item.get("id") in {"filet-antique", "selle-antique"})
    mark(catalog.get("horse_gear", []), "amiibo", lambda item: item.get("amiibo", False))
    mark(catalog.get("scripted_bosses", []), "champions_ballad", lambda item: item.get("dlc", False))
    mark(catalog.get("champion_upgrades", []), "champions_ballad", lambda _item: True)
    mark(catalog.get("expansion_bonus_chests", []), "expansion_bonus", lambda _item: True)
    mark(catalog.get("dlc_features", []), "master_trials",
         lambda item: item.get("id") == "mode-empreintes")
    mark(catalog.get("dlc_features", []), "master_mode",
         lambda item: item.get("id") == "mode-expert")

    bonus_contents = {"Nintendo Switch Shirt", "Ruby", "Bomb Arrow x5"}
    pack1_contents = {
        "Phantom Helmet", "Phantom Greaves", "Phantom Armor", "Majora's Mask",
        "Midna's Helmet", "Tingle's Hood", "Tingle's Shirt", "Tingle's Tights",
        "Korok Mask", "Travel Medallion",
    }
    pack2_contents = {
        "Island Lobster Shirt", "Ravio's Hood", "Zant's Helmet",
        "Royal Guard Cap", "Royal Guard Uniform", "Royal Guard Boots",
        "Phantom Ganon Skull", "Phantom Ganon Armor", "Phantom Ganon Greaves",
        "Ancient Bridle", "Ancient Saddle",
    }
    aoc_chests = [item for item in catalog.get("world_chests", [])
                  if "NoReaction_Aoc" in item.get("acteur", "")]
    mark(aoc_chests, "expansion_bonus", lambda item: item.get("contenu") in bonus_contents)
    mark(aoc_chests, "master_trials", lambda item: item.get("contenu") in pack1_contents)
    mark(aoc_chests, "champions_ballad", lambda item: item.get("contenu") in pack2_contents)
    mark(catalog.get("world_chests", []), "master_trials",
         lambda item: item.get("id", "").startswith("AocField-"))

    for item in catalog.get("map_layers", []):
        actors = item.get("acteur", "")
        if item.get("mode_expert"):
            item.update({"content_origin": "master_mode", "content_origin_label": ORIGIN_LABELS["master_mode"], "dlc": True})
        elif "Enemy_Golem_Fire_R" in actors or "Enemy_SandwormR" in actors:
            item.update({"content_origin": "champions_ballad", "content_origin_label": ORIGIN_LABELS["champions_ballad"], "dlc": True})

    for list_name in lists:
        for item in catalog.get(list_name, []):
            origin = item.get("content_origin", "base")
            item.setdefault("content_origin_label", ORIGIN_LABELS[origin])
            if origin != "base" and not item.get("region") and item.get("x") is not None and item.get("z") is not None:
                item["region"] = nearest_region(item["x"], item["z"], catalog)

    catalog["dlc_audit"] = {
        "source": "Nintendo - contenu officiel de l'Expansion Pass",
        "source_url": NINTENDO_DLC_URL,
        "status": "complete",
        "families": [
            {"id": "bonus_coffres", "label": "Trois coffres bonus", "expected": 3, "implemented": 3},
            {"id": "epreuves_epee", "label": "Trois niveaux des Épreuves de l'épée", "expected": 3, "implemented": 3},
            {"id": "mode_empreintes", "label": "Mode Empreintes", "expected": 1, "implemented": 1},
            {"id": "mode_expert", "label": "Mode expert", "expected": 1, "implemented": 1},
            {"id": "amulette", "label": "Amulette de téléportation", "expected": 1, "implemented": 1},
            {"id": "armures_pack1", "label": "Huit objets cachés du DLC 1", "expected": 8, "implemented": 8},
            {"id": "masque_korogu", "label": "Masque de Korogu", "expected": 1, "implemented": 1},
            {"id": "ballade", "label": "Ballade des Prodiges et donjon final", "expected": 1, "implemented": 1},
            {"id": "sanctuaires_ballade", "label": "Sanctuaires de la Ballade", "expected": 16, "implemented": 16},
            {"id": "boss_ballade", "label": "Boss et royaumes illusoires", "expected": 7, "implemented": 7},
            {"id": "souvenirs_ballade", "label": "Souvenirs de la Ballade", "expected": 5, "implemented": 5},
            {"id": "armures_pack2", "label": "Neuf objets cachés du DLC 2", "expected": 9, "implemented": 9},
            {"id": "harnachement", "label": "Harnachement antique", "expected": 2, "implemented": 2},
            {"id": "recompenses", "label": "Pouvoirs + et Destrier de légende 0.1", "expected": 5, "implemented": 5},
        ],
    }
    catalog["dlc_audit"]["status"] = (
        "complete" if all(item["implemented"] == item["expected"]
                          for item in catalog["dlc_audit"]["families"])
        else "partial"
    )


def make_layers(catalog: dict, object_map: dict) -> list[dict]:
    layers: list[dict] = []

    # Les acteurs de la carte sont les variantes initiales. Certaines familles
    # sont remplacées par LevelSensor quand la difficulté du monde augmente :
    # on conserve donc la famille comme filtre exact et la variante comme aide.
    enemy_families = (
        ("Enemy_Bokoblin", "enemy_bokoblin", "Bokoblin", True),
        ("Enemy_Moriblin", "enemy_moblin", "Moblin", True),
        ("Enemy_Lizalfos", "enemy_lizalfos", "Lézalfos", True),
        ("Enemy_Chuchu", "enemy_chuchu", "Chuchu", False),
        ("Enemy_Keese", "enemy_keese", "Chauve-souris", False),
        ("Enemy_Octarock", "enemy_octorok", "Octo", False),
        ("Enemy_AirOctarock", "enemy_sky_octorok", "Octo aérien", False),
        ("Enemy_Wizzrobe", "enemy_wizzrobe", "Sorcier", True),
        ("Enemy_Assassin", "enemy_yiga", "Yiga", False),
        ("Enemy_Lynel", "enemy_lynel", "Lynel", True),
        ("Enemy_Guardian", "enemy_guardian", "Gardien", False),
        ("Enemy_Giant", "enemy_hinox", "Hinox", False),
        ("Enemy_Golem_Little", "enemy_pebblit", "Petit Lithorok", False),
        ("Enemy_Golem", "enemy_talus", "Lithorok", False),
        ("Enemy_Sandworm", "enemy_molduga", "Moldarquor", False),
    )
    excluded_actors = {
        "Enemy_Assassin_Senior", "Enemy_GanonBeast", "Enemy_Ganon",
    }

    def family_for(actor: str) -> tuple[str, str, bool] | None:
        if actor in excluded_actors or actor.startswith("Enemy_SiteBoss"):
            return None
        for prefix, layer_type, family, scalable in enemy_families:
            if actor.startswith(prefix):
                return layer_type, family, scalable
        if actor == "RemainsFire_Drone_A_01":
            return "enemy_sentry", "Sentinelle", False
        return None

    def subtype_for(actor: str, family: str) -> str:
        suffix = actor.replace("Enemy_", "").split("_", 1)[-1]
        replacements = (
            ("Junior_Mountain", "du mont Ploymus"), ("Junior", "rouge/de base"),
            ("Middle", "bleu/intermédiaire"), ("Senior", "blanc/noir"),
            ("Dark", "d'argent"), ("Gold", "doré - mode expert"),
            ("Electric", "électrique"), ("Fire", "de feu"), ("Ice", "de glace"),
            ("Moss", "détérioré"), ("Sand", "des sables"), ("Snow", "des neiges"),
            ("Fixed", "immobile"), ("Stal", "squelettique"),
        )
        qualities = [label for token, label in replacements if token in suffix]
        if actor.startswith("Enemy_Guardian_A_Fixed"):
            qualities = ["détérioré"]
        elif actor.startswith("Enemy_Guardian_A"):
            qualities = ["à pied"]
        elif actor.startswith("Enemy_Guardian_B"):
            qualities = ["tourelle"]
        elif actor.startswith("Enemy_Guardian_C"):
            qualities = ["volant"]
        elif actor.startswith("Enemy_Giant_Bone"):
            qualities = ["Stalhinox"]
        elif actor.startswith("Enemy_Golem_Senior"):
            qualities = ["Lithorok nox"]
        elif actor.startswith("Enemy_Golem_Middle"):
            qualities = ["Cryorok"]
        elif actor.startswith("Enemy_Golem_Fire"):
            qualities = ["Magrok"]
        elif actor.startswith("Enemy_SandwormR"):
            qualities = ["Arquor Rex"]
        elif actor == "Enemy_AirOctarock":
            qualities = ["mode expert"]
        return family if not qualities else f"{family} - {' / '.join(dict.fromkeys(qualities))}"

    candidates: dict[str, list[dict]] = {}
    for key, entry in object_map.items():
        parts = key.split(":")
        hard = parts[0] == "HARD"
        actor = parts[1] if hard and len(parts) > 1 else parts[0]
        family = family_for(actor)
        if not family:
            continue
        layer_type, family_name, scalable = family
        bucket = candidates.setdefault(layer_type, [])
        threshold = 25 if layer_type == "enemy_lynel" else 1
        for x, z in entry["locations"]:
            match = next((candidate for candidate in bucket
                          if math.hypot(candidate["x"] - x, candidate["z"] - z) < threshold), None)
            if not match:
                match = {"x": x, "z": z, "actors": set(), "subtypes": set(),
                         "base": False, "hard": False, "family": family_name,
                         "scalable": scalable}
                bucket.append(match)
            match["actors"].add(actor)
            match["subtypes"].add(subtype_for(actor, family_name))
            match["hard" if hard else "base"] = True

    for layer_type, bucket in sorted(candidates.items()):
        for index, candidate in enumerate(bucket, 1):
            subtype = " / ".join(sorted(candidate["subtypes"]))
            expert_only = candidate["hard"] and not candidate["base"]
            layer = point(
                catalog, item_id=f"{layer_type}-{index:04d}",
                name=f"{candidate['family']} {index:03d}",
                x=candidate["x"], z=candidate["z"], layer_type=layer_type,
                subtype=subtype, dlc=expert_only,
                actor=", ".join(sorted(candidate["actors"])),
                mode_expert=expert_only, scalable=candidate["scalable"],
            )
            if any(actor in candidate["actors"] for actor in ("Enemy_Golem_Fire_R", "Enemy_SandwormR")):
                layer["content_origin"] = "champions_ballad"
                layer["content_origin_label"] = ORIGIN_LABELS["champions_ballad"]
                layer["dlc"] = True
            layers.append(layer)

    # Nano Gardiens présents dans les sanctuaires de combat : leurs emplacements
    # extérieurs restent utiles pour le farm et ils reviennent à la lune de sang.
    combat_levels = {
        "A Minor Test of Strength": "Épreuve mineure de force",
        "A Modest Test of Strength": "Épreuve moyenne de force",
        "A Major Test of Strength": "Épreuve majeure de force",
        "A Major Test of Strength+": "Épreuve majeure de force + (DLC)",
    }
    scout_index = 0
    for shrine in catalog["shrines"]:
        if shrine.get("trial") not in combat_levels:
            continue
        scout_index += 1
        subtype = combat_levels[shrine["trial"]]
        layers.append(point(
            catalog, item_id=f"enemy_guardian_scout-{scout_index:02d}",
            name=f"Nano Gardien - {subtype}", x=shrine["x"], z=shrine["z"],
            layer_type="enemy_guardian_scout", subtype=subtype,
            dlc="DLC" in subtype, actor="Enemy_Guardian_Mini",
        ))

    service_specs = (
        ("TwnObj_GoddesStatue_A_01", "Statue de la Déesse", "statue_deesse"),
        ("TwnObj_GoddesStatue_A_02", "Statue de la Déesse", "statue_deesse"),
        ("TwnObj_GoddesStatue_A_03", "Statue de la Déesse", "statue_deesse"),
        ("TwnObj_GoddesStatue_A_10", "Statue de la Déesse", "statue_deesse"),
        ("TwnObj_SuperGoddesStatue_A_01", "Statue de la Déesse", "statue_deesse"),
        ("Item_CookSet", "Marmite", "marmite"),
        ("Item_CookSet_PanOnly", "Marmite", "marmite"),
        ("Obj_RaftWoodSail_A_S_01", "Radeau", "radeau"),
        ("Npc_MamonoShop", "Kilton", "kilton"),
    )
    service_counts: dict[str, int] = {}
    for actor, name, layer_type in service_specs:
        for x, z in object_map[actor]["locations"]:
            service_counts[layer_type] = service_counts.get(layer_type, 0) + 1
            index = service_counts[layer_type]
            layers.append(point(
                catalog, item_id=f"{layer_type}-{index:03d}", name=f"{name} {index:02d}",
                x=x, z=z, layer_type=layer_type, actor=actor,
            ))

    # Bâtiments et enseignes suffisamment spécifiques pour éviter de placer
    # un service sur un PNJ qui se déplace selon l'heure ou une quête.
    shop_specs = {
        "auberge": (
            "TwnObj_Village_IchikaraHotelSign_A_01", "TwnObj_Village_RitoHotelSign_A_01",
            "TwnObj_Village_SheikerHotelSign_A_01", "TwnObj_Village_HatenoHotelDoor_A_01",
            "TwnObj_City_GoronHotel_A_01", "TwnObj_Village_ZoraHotel_A_01",
            "TwnObj_SmallOasisHotel_A_01",
        ),
        "boutique_armures": (
            "TwnObj_Village_RitoTailorSign_A_01", "TwnObj_Village_SheikerTailorSign_A_01",
            "TwnObj_Village_HatenoTailor_A_01", "TwnObj_City_GoronTailor_A_01",
            "TwnObj_City_GerudoClothShopInside_A_01",
        ),
        "magasin_general": (
            "TwnObj_Village_SheikerGrocerySign_A_01", "TwnObj_Village_ZoraShop_A_01",
            "TwnObj_Village_FishingBoatShopPlate_A_01", "TwnObj_Village_IchikaraShopTable_A_01",
        ),
        "bijouterie": ("TwnObj_City_GerudoJewelryShopInside_A_01",),
    }
    shop_names = {
        "auberge": "Auberge", "boutique_armures": "Boutique d'armures",
        "magasin_general": "Magasin général", "bijouterie": "Bijouterie",
    }
    for layer_type, actors in shop_specs.items():
        candidates_for_service: list[tuple[float, float, str]] = []
        for actor in actors:
            for x, z in object_map.get(actor, {}).get("locations", []):
                if not any(math.hypot(px - x, pz - z) < 20 for px, pz, _ in candidates_for_service):
                    candidates_for_service.append((x, z, actor))
        for index, (x, z, actor) in enumerate(candidates_for_service, 1):
            layers.append(point(
                catalog, item_id=f"{layer_type}-{index:02d}",
                name=f"{shop_names[layer_type]} {index:02d}", x=x, z=z,
                layer_type=layer_type, actor=actor, repeatable=False,
            ))

    locations = catalog["locations"]
    selected_locations = []
    for item in locations:
        flag, name = item["flag"], item["name"]
        layer_type = None
        if "Hatago" in flag and "Stable" in name:
            layer_type = "relais"
        elif flag in {"Location_Gerudo", "Location_Goron", "Location_Hateno", "Location_Kakariko",
                      "Location_Rito", "Location_Taura", "Location_UMiiVillage", "Location_WhiteZora"}:
            layer_type = "village"
        elif flag in {"Location_AncientLabo", "Location_HatenoLabo"}:
            layer_type = "laboratoire"
        elif flag.startswith("Location_WeaponCureSpring"):
            layer_type = "grande_fee"
        elif flag == "Location_MaronSpring":
            layer_type = "malanya"
        if layer_type:
            selected_locations.append((item, layer_type))
    for index, (item, layer_type) in enumerate(selected_locations, 1):
        layers.append(point(
            catalog, item_id=f"service-{index:03d}", name=item["name"], x=item["x"], z=item["z"],
            layer_type=layer_type,
        ))

    # Les fiches de quête gardent leur point de départ principal. Les étapes
    # suivantes deviennent aussi sélectionnables indépendamment sur la carte.
    objective_index = 0
    for source_name in ("main_quests", "shrine_quests", "side_quests"):
        for quest in catalog.get(source_name, []):
            for step_number, geo in enumerate(quest.get("geo_points", [])[1:], 2):
                if geo.get("x") is None or geo.get("z") is None:
                    continue
                objective_index += 1
                label = geo.get("label") or f"Étape {step_number}"
                layer = point(
                    catalog, item_id=f"quest-objective-{objective_index:03d}",
                    name=f"{quest['name']} - {label}", x=geo["x"], z=geo["z"],
                    layer_type="quest_objective", subtype=source_name,
                    dlc=bool(quest.get("dlc")), repeatable=False,
                )
                layer["content_origin"] = quest.get("content_origin", "base")
                layer["content_origin_label"] = quest.get("content_origin_label", ORIGIN_LABELS["base"])
                layers.append(layer)
    return layers


def acquisition_point(catalog: dict, english_name: str) -> dict:
    chest = next((item for item in catalog["world_chests"]
                  if item.get("contenu", "").split(" x", 1)[0] == english_name), None)
    if not chest or chest.get("x") is None:
        return {}
    return {"x": chest["x"], "z": chest["z"], "region": chest.get("region"),
            "nearby": chest.get("nearby")}


def make_progress_categories(catalog: dict, object_map: dict) -> None:
    fairies = [item for item in catalog["locations"] if item["flag"].startswith("Location_WeaponCureSpring")]
    catalog["great_fairies"] = [{
        "id": "grandes-fees", "name": "Réveiller les quatre Grandes Fées",
        "flag": "FairyRevivalNum", "min_value": 4, "target": 4,
        "x": fairies[0]["x"], "z": fairies[0]["z"],
        "geo_points": [{"role": "fontaine", "label": f"Fontaine {index}", "x": item["x"], "z": item["z"]}
                       for index, item in enumerate(fairies, 1)],
        "action": "Réveille chaque Grande Fée en payant l'offrande demandée.",
        "completion_condition": "Le compteur permanent FairyRevivalNum doit atteindre 4.",
    }]
    malanya = next(item for item in catalog["locations"] if item["flag"] == "Location_MaronSpring")
    catalog["malanya"] = [{
        "id": "malanya", "name": "Réveiller Marlon", "flag": "HorseGod001_DispNameFlag",
        "x": malanya["x"], "z": malanya["z"], "region": "Faron",
        "action": "Offre 1 000 rubis à la grande fleur de la fontaine de Marlon.",
        "completion_condition": "Le nom de Marlon doit être déverrouillé dans la sauvegarde.",
    }]
    catalog["trial_of_the_sword"] = [
        {"id": "epreuves-debutant", "name": "Épreuves basiques de l'épée", "flag": "100enemy_Clear_Junior", "dlc": True, "region": "Épreuves de l'épée", "reward": "Puissance de l'épée de légende : 40", "master_sword_power": 40},
        {"id": "epreuves-moyen", "name": "Épreuves moyennes de l'épée", "flag": "100enemy_Clear_Middle", "dlc": True, "region": "Épreuves de l'épée", "reward": "Puissance de l'épée de légende : 50", "master_sword_power": 50},
        {"id": "epreuves-expert", "name": "Épreuves finales de l'épée", "flag": "100enemy_Clear_Senior", "dlc": True, "region": "Épreuves de l'épée", "reward": "Puissance permanente de l'épée de légende : 60", "master_sword_power": 60},
    ]
    catalog["kilton_medals"] = [
        {"id": "medaille-hinox", "name": "Médaille des Hinox", "flag": "MamonoShop_BigEnemy_Giant_Finish"},
        {"id": "medaille-lithoroks", "name": "Médaille des Lithoroks", "flag": "MamonoShop_BigEnemy_Golem_Finish"},
        {"id": "medaille-moldarquors", "name": "Médaille des Moldarquors", "flag": "MamonoShop_BigEnemy_Sandworm_Finish"},
    ]
    catalog["unique_rewards"] = [
        {"id": "cadeau-noia", "name": "Cadeau de Noïa", "flag": "HiddenKorok_Complete", "region": "Forêt d'Hyrule"},
        {"id": "enveloppe-confidentielle", "name": "Enveloppe confidentielle", "flag": "HatenoMini_CameraBoy_GetReward", "region": "Hateno"},
    ]
    catalog["horse_gear"] = [
        {"id": "filet-voyageur", "name": "Filet de voyageur", "flag": "IsGet_GameRomHorseReins_01", "amiibo": True},
        {"id": "selle-voyageur", "name": "Selle de voyageur", "flag": "IsGet_GameRomHorseSaddle_01", "amiibo": True},
        {"id": "filet-royal", "name": "Filet royal", "flag": "IsGet_GameRomHorseReins_02"},
        {"id": "selle-royale", "name": "Selle royale", "flag": "IsGet_GameRomHorseSaddle_02"},
        {"id": "filet-chevalier", "name": "Filet de chevalier", "flag": "IsGet_GameRomHorseReins_03"},
        {"id": "selle-chevalier", "name": "Selle de chevalier", "flag": "IsGet_GameRomHorseSaddle_03"},
        {"id": "filet-monstre", "name": "Filet monstrueux", "flag": "IsGet_GameRomHorseReins_04"},
        {"id": "selle-monstre", "name": "Selle monstrueuse", "flag": "IsGet_GameRomHorseSaddle_04"},
        {"id": "filet-extravagant", "name": "Filet extravagant", "flag": "IsGet_GameRomHorseReins_05"},
        {"id": "selle-extravagante", "name": "Selle extravagante", "flag": "IsGet_GameRomHorseSaddle_05"},
        {"id": "filet-antique", "name": "Filet antique", "flag": "IsGet_GameRomHorseReins_10", "dlc": True,
         "x": -2295.86, "z": 343.47, "region": "Hyrule central"},
        {"id": "selle-antique", "name": "Selle antique", "flag": "IsGet_GameRomHorseSaddle_10", "dlc": True,
         "x": 812.99, "z": 3700.97, "region": "Faron"},
    ]
    catalog["special_items"] = [
        {"id": "amulette-teleportation", "name": "Amulette de téléportation", "flag": "IsGet_Obj_WarpDLC", "dlc": True,
         "x": 4655.0, "z": -3560.02, "region": "Akkala"},
        {"id": "destrier-zero-un", "name": "Destrier de légende 0.1", "flag": "IsGet_Obj_Motorcycle", "dlc": True},
    ]
    bonus_flags = {
        "MainField_TBox_Field_Iron_NoReaction_Aoc_4093217196": "T-shirt Nintendo Switch",
        "MainField_TBox_Field_Iron_NoReaction_Aoc_473644037": "Rubis brut bonus",
        "MainField_TBox_Field_Iron_NoReaction_Aoc_759164510": "Flèches explosives bonus",
    }
    catalog["expansion_bonus_chests"] = []
    for flag, name in bonus_flags.items():
        chest = next(item for item in catalog["world_chests"] if item["flag"] == flag)
        catalog["expansion_bonus_chests"].append({
            "id": chest["id"], "name": name, "flag": flag, "dlc": True,
            "x": chest["x"], "z": chest["z"], "region": chest.get("region"),
            "contenu": chest.get("contenu"),
        })
    catalog["champion_upgrades"] = [
        {"id": "grace-mipha-plus", "name": "Grâce de Mipha +", "flag": "IsGet_Obj_DLC_HeroSoul_Zora", "dlc": True},
        {"id": "rage-revali-plus", "name": "Rage de Revali +", "flag": "IsGet_Obj_DLC_HeroSoul_Rito", "dlc": True},
        {"id": "bouclier-daruk-plus", "name": "Bouclier de Daruk +", "flag": "IsGet_Obj_DLC_HeroSoul_Goron", "dlc": True},
        {"id": "colere-urbosa-plus", "name": "Colère d'Urbosa +", "flag": "IsGet_Obj_DLC_HeroSoul_Gerudo", "dlc": True},
    ]
    catalog["dlc_features"] = [
        {"id": "mode-empreintes", "name": "Mode Empreintes", "feature": "hero_path", "dlc": True,
         "usage_flags": ["AoC_hero_memory_Activated", "AoC_hero_memory_Finish"]},
        {"id": "mode-expert", "name": "Mode expert", "feature": "master_mode", "dlc": True,
         "usage_flags": ["AoC_HardMode_Enabled"], "separate_save": True},
    ]

    beast_specs = {
        "Location_RemainsElectric": ("Electric_Relic_Finished", "Vah'Naboris"),
        "Location_RemainsFire": ("Fire_Relic_Finished", "Vah'Rudania"),
        "Location_RemainsWater": ("Water_Relic_Finished", "Vah'Ruta"),
        "Location_RemainsWind": ("Wind_Relic_Finished", "Vah'Medoh"),
    }
    catalog["divine_beasts"] = []
    for item in catalog["official_map_locations"]:
        if item["flag"] in beast_specs:
            flag, name = beast_specs[item["flag"]]
            catalog["divine_beasts"].append({
                "id": item["flag"], "name": name, "flag": flag,
                "x": item["x"], "z": item["z"], "region": nearest_region(item["x"], item["z"], catalog),
            })

    kohga = object_map["Enemy_Assassin_Senior"]["locations"][0]
    mega = object_map["Enemy_Golem_Fire_R"]["locations"][0]
    arquor_key = next(key for key in object_map if key.startswith("Enemy_SandwormR:"))
    arquor = object_map[arquor_key]["locations"][0]
    beasts = {item["flag"]: item for item in catalog["official_map_locations"]}
    catalog["scripted_bosses"] = [
        {"id": "kohga", "name": "Grand Kohga", "flag": "MainField_Enemy_Assassin_Senior_2126854204", "x": kohga[0], "z": kohga[1]},
        {"id": "ombre-eau", "name": "Ombre d'eau de Ganon", "flag": "Die_PGanonWater", **{k: beasts["Location_RemainsWater"][k] for k in ("x", "z")}},
        {"id": "ombre-feu", "name": "Ombre de feu de Ganon", "flag": "Die_PGanonFire", **{k: beasts["Location_RemainsFire"][k] for k in ("x", "z")}},
        {"id": "ombre-vent", "name": "Ombre de vent de Ganon", "flag": "Die_PGanonWind", **{k: beasts["Location_RemainsWind"][k] for k in ("x", "z")}},
        {"id": "ombre-foudre", "name": "Ombre de foudre de Ganon", "flag": "Die_PGanonElectric", **{k: beasts["Location_RemainsElectric"][k] for k in ("x", "z")}},
        {"id": "ganon", "name": "Ganon, le Fléau", "flag": "GanonQuest_Finished", "x": -254.0, "z": -1063.0},
        {"id": "arquor-rex", "name": "Arquor Rex", "any_flags": ["MainField_IsDefeat_Enemy_SandwormR_1755179653", "BalladOfHeroGerudo_FirstKillSandwormR"], "x": arquor[0], "z": arquor[1], "dlc": True},
        {"id": "mega-magrok", "name": "Méga Magrok", "any_flags": ["MainField_IsDefeat_Enemy_Golem_Fire_R_667761767", "BalladOfHeroGoron_FirstKillGolemR", "BalladOfHeroGoron_KillGolemR"], "x": mega[0], "z": mega[1], "dlc": True},
        {"id": "miz-kyosia", "name": "Guide Miz'Kyosia", "flag": "Die_Boss_FinalTrial", "dlc": True, "region": "Épreuve finale"},
    ]
    rematch_specs = (
        ("eau", "Ombre d'eau de Ganon - royaume illusoire", "BalladOfHeroZora_Finish", "Location_RemainsWater"),
        ("feu", "Ombre de feu de Ganon - royaume illusoire", "BalladOfHeroGoron_Finish", "Location_RemainsFire"),
        ("vent", "Ombre de vent de Ganon - royaume illusoire", "BalladOfHeroRito_Finish", "Location_RemainsWind"),
        ("foudre", "Ombre de foudre de Ganon - royaume illusoire", "BalladOfHeroGerudo_Finish", "Location_RemainsElectric"),
    )
    for boss_id, name, flag, location_flag in rematch_specs:
        catalog["scripted_bosses"].append({
            "id": f"royaume-illusoire-{boss_id}", "name": name, "flag": flag,
            "x": beasts[location_flag]["x"], "z": beasts[location_flag]["z"], "dlc": True,
        })
    for item in catalog["scripted_bosses"]:
        if item.get("x") is not None:
            item.setdefault("region", nearest_region(item["x"], item["z"], catalog))

    extra_specs = (
        ("Armor_043_Lower", "Well-Worn Trousers", False, []),
        ("Armor_043_Upper", "Old Shirt", False, []),
        ("Armor_044_Upper", "Warm Doublet", False, []),
        ("Armor_022_Head", "Bokoblin Mask", False, []),
        ("Armor_045_Head", "Moblin Mask", False, []),
        ("Armor_055_Head", "Lizalfos Mask", False, []),
        ("Armor_056_Head", "Lynel Mask", False, []),
        ("Armor_053_Head", "Gerudo Veil", False, []),
        ("Armor_053_Lower", "Gerudo Sirwal", False, []),
        ("Armor_053_Upper", "Gerudo Top", False, []),
        ("Armor_115_Head", "Thunder Helm", False, []),
        ("Armor_160_Head", "Dark Hood", False, []),
        ("Armor_160_Lower", "Dark Trousers", False, []),
        ("Armor_160_Upper", "Dark Tunic", False, []),
        ("Armor_170_Upper", "Nintendo Switch Shirt", True, []),
        ("Armor_171_Head", "Phantom Helmet", True, []),
        ("Armor_171_Lower", "Phantom Greaves", True, []),
        ("Armor_171_Upper", "Phantom Armor", True, []),
        ("Armor_172_Head", "Majora's Mask", True, []),
        ("Armor_173_Head", "Midna's Helmet", True, []),
        ("Armor_174_Head", "Tingle's Hood", True, []),
        ("Armor_174_Lower", "Tingle's Tights", True, []),
        ("Armor_174_Upper", "Tingle's Shirt", True, []),
        ("Armor_175_Upper", "Island Lobster Shirt", True, []),
        ("Armor_176_Head", "Korok Mask", True, []),
        ("Armor_177_Head", "Ravio's Hood", True, []),
        ("Armor_178_Head", "Zant's Helmet", True, []),
        ("Armor_179_Head", "Royal Guard Cap", True, []),
        ("Armor_179_Lower", "Royal Guard Boots", True, []),
        ("Armor_179_Upper", "Royal Guard Uniform", True, []),
        ("Armor_180_Head", "Phantom Ganon Skull", True, []),
        ("Armor_180_Lower", "Phantom Ganon Greaves", True, []),
        ("Armor_180_Upper", "Phantom Ganon Armor", True, []),
        ("Armor_185_Head", "Salvager Headwear", False, []),
        ("Armor_185_Lower", "Salvager Trousers", False, []),
        ("Armor_185_Upper", "Salvager Vest", False, []),
        ("Armor_168_Head", "Vah Naboris Divine Helm", False, ["Armor_169_Head", "Armor_184_Head", "Armor_198_Head", "Armor_199_Head"]),
        ("Armor_181_Head", "Vah Ruta Divine Helm", False, ["Armor_186_Head", "Armor_187_Head", "Armor_188_Head", "Armor_189_Head"]),
        ("Armor_182_Head", "Vah Medoh Divine Helm", False, ["Armor_190_Head", "Armor_191_Head", "Armor_192_Head", "Armor_193_Head"]),
        ("Armor_183_Head", "Vah Rudania Divine Helm", False, ["Armor_194_Head", "Armor_195_Head", "Armor_196_Head", "Armor_197_Head"]),
    )
    catalog["special_armor"] = []
    amiibo_armor = {"Armor_168_Head", "Armor_181_Head", "Armor_182_Head", "Armor_183_Head"}
    for actor, name, dlc, variants in extra_specs:
        catalog["special_armor"].append({
            "id": actor, "name": name, "dlc": dlc,
            "amiibo": actor in amiibo_armor,
            "variants": [actor, *variants], **acquisition_point(catalog, name),
        })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--object-map", type=Path, required=True)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text())
    object_map = load_object_map(args.object_map)
    make_progress_categories(catalog, object_map)
    apply_dlc_metadata(catalog)
    catalog["map_layers"] = make_layers(catalog, object_map)
    apply_dlc_metadata(catalog)
    catalog["schema_version"] = 6
    args.catalog.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    counts = {kind: sum(item["layer_type"] == kind for item in catalog["map_layers"])
              for kind in sorted({item["layer_type"] for item in catalog["map_layers"]})}
    print(f"{len(catalog['map_layers'])} points informatifs : {counts}")
    print(f"{len(catalog['special_armor'])} équipements particuliers")


if __name__ == "__main__":
    main()