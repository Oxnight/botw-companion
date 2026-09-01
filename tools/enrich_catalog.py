#!/usr/bin/env python3
"""Enrichit le catalogue avec les règles de progression documentées.

Ce générateur n'est pas exécuté chez l'utilisateur. Il traduit les offsets du
BOTW Save File Mapper en noms de GameData flags, puis ne distribue que ces
règles portables avec l'application.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
import unicodedata
import html


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = value.lower().replace("ex ", "")
    return re.sub(r"[^a-z0-9]", "", value)


SIDE_FLAGS = [
    "MinamihateeluMini_touzoku_Finish", "OldKorok_Help_Finish",
    "HutagoHatago_Ch_001_Finish", "Kakariko_Cha_003_Finish",
    "Kakariko_Ch_005_Finish", "Kakariko_Ch_Cooking2_Finish",
    "Kakariko_Ch_Cooking3_Finish", "Kakariko_Ch_Cooking4_Finish",
    "Kakariko_Ch_006_Finish", "Kakariko_Cha_001_Finish",
    "Kakariko_Ch_004_Finish", "HatenoMini_DeathDevil_Finish",
    "HatenoMini_WeaponMania_Finish", "HatenoMini_LoveInsects_Finish",
    "HatenoMini_GoatThief_Finished", "HatenoMini_BlueFire_Finish",
    "Hateno_SheikPad_PowerUp_Finish", "HatenoMini_CameraBoy_Finish",
    "HateeluMini_Treasure_Finish", "HatenoMini_MyHome_Finish",
    "UMiiMini_MakeVillage_Finish", "LetterErrand_Finished",
    "ZoraMini_DiveChallenge_Finish", "RinelSearch_Finish",
    "Zora_FlogMini_Finish", "Giant_ZoraMini_Finish",
    "ZoraMini_HarvestingStone_Finish", "ZoraMini_FlowedWife_Finish",
    "Relief_Landing_Finish", "LanayruMini_ZoraRelief_Finish",
    "UotoriMini_RecipeSea_Finish", "UotoriMini_SinkTreasure_Finish",
    "UotoriMini_RecoverBay_Finish", "FironeMini_HeartPond_Finish",
    "FironeMini_TerribleThunder_Finish", "FironeMini_GiantHorse_Finish",
    "FironeMini_HorseEnemy_Finish", "Gerudo_HorseBuyer_Finish",
    "SnowMountainRescue_Finished", "Gerudo_tsukamidake_Finish",
    "GoronCityMini_BeatGolem_Finish", "GerudoMiniJewel_Finished",
    "Gerudo_Ch_SecretClub_Finish", "Gerudo_Ch_SandWarm_Finish",
    "Gerudo_Ch_SnowMT_Finish", "Gerudo_Ch_SnowBoots_Finish",
    "Gerudo_Ch_Helmet_Finish", "Gerudo_Ch_Poison_Finish",
    "Gerudo_Ch_FindingValetta_Finish", "RitoUmayadoMini_HotRecipe_Finish",
    "RitoMini_Flint_Finish", "RitoMini_Cook_Finish",
    "RitoMini_IceGolem_Finish", "Rito_KeelSearch_Finish",
    "SetugenUmayadoMini_Umahonephoto_Finish", "HyrulePlainMini_Balloon_Finish",
    "KorokMini_RodShiren_Finish", "KorokMini_KorokShiren_Finish",
    "RitoRabitMountain_Finish", "MarittaMini_BigWhales_Finish",
    "CompleteDungeon_Finish", "KorokMini_RiddleShiren_Finish",
    "TabantaBridgeMini_Sundial_Finish", "RiversideMini_CastleWeapon_Finish",
    "Remains_Fancier_Finish", "My_Hero_Finish",
    "RiversideMini_RoyalRecipe_Finish", "HyruleDepthMini_WhiteHorse_Finish",
    "SanrokuMini_Lizard_Finish", "GoronCamp_Finish",
    "GoronMini_WallCrackTBox_Finish", "GoronMini_ImportGem_Finish",
    "UMiiMini_GiveCake_Finish", "UMiiMini_RichmansHobby_Finish",
    "HigakkareMini_StrangeMan_Finish", "MinakkareMini_Dragonfly_Finish",
    "100enemy_Finish", "TreasureHunt_touzoku01_Finish",
    "TreasureHunt_touzoku02_Finish", "TreasureHunt_touzoku03_Finish",
    "TreasureHunt_touzoku04_Finish", "TreasureHunt_touzoku05_Finish",
    "TreasureHunt_touzoku06_Finish", "bf2_collabo_Finish",
    "TreasureHunt_touzoku07_Finish", "RiversideMini_CastleWeapon_Finish",
    "TreasureHunt_touzoku08_Finish", "TreasureHunt01_Finish",
    "TreasureHunt02_Finish", "TreasureHunt03_Finish",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", type=Path, required=True)
    ap.add_argument("--effectmap", type=Path, required=True)
    ap.add_argument("--layout-save", type=Path, required=True)
    ap.add_argument("--hashes", type=Path, required=True)
    ap.add_argument("--names", type=Path, required=True)
    ap.add_argument("--objmap", type=Path, required=True)
    ap.add_argument("--checklist", type=Path, required=True)
    ap.add_argument("--questmsg", type=Path, required=True)
    ap.add_argument("--waypoint-map", type=Path, required=True)
    ap.add_argument("--chests", type=Path, action="append", default=[])
    args = ap.parse_args()

    catalog = json.loads(args.catalog.read_text())
    effects = json.loads(args.effectmap.read_text())
    save = args.layout_save.read_bytes()
    hash_names = {int(h): name for h, _type, name in
                  (line.split(";", 2) for line in args.hashes.read_text().splitlines())}

    def flag_at(offset: int) -> str | None:
        if offset < 4 or offset > len(save):
            return None
        return hash_names.get(struct.unpack_from("<I", save, offset - 4)[0])

    def entries(rule: dict) -> list[dict]:
        result = []
        for entry in rule.get("entries", []):
            flag = flag_at(entry["offset"])
            if flag:
                result.append({"flag": flag, "value": entry.get("value", True)})
        return result

    def state_rule(group: str, slug: str, state: str, substate: str | None = None) -> list[dict]:
        node = effects[group][slug][state]
        if substate and substate in node:
            node = node[substate]
        result = entries(node)
        if not result:
            # Quelques quêtes n'ont pas leur propre flag de fin : leur
            # dépendance dure pointe vers le flag qui fait foi dans le jeu.
            for dep in node.get("harddependencies", []):
                bits = dep.split(".")
                if len(bits) >= 3 and bits[0] in effects and bits[1] in effects[bits[0]]:
                    depnode = effects[bits[0]][bits[1]]
                    for part in bits[2:]:
                        depnode = depnode.get(part, {})
                    result.extend(entries(depnode))
        return result

    def build_effect_items(group: str, source: list, name_getter, complete_state="complete") -> list[dict]:
        lookup = {norm(name_getter(item)): item for item in source}
        # Deux titres officiels diffèrent uniquement par l'article dans le mapper.
        if group == "shrinequests":
            lookup["atestofwill"] = lookup.get("testofwill")
        output = []
        for slug in effects[group]:
            original = lookup.get(slug)
            if original is None:
                continue
            item = dict(original) if isinstance(original, dict) else {"name": original}
            item.update({"id": slug, "rule": state_rule(group, slug, complete_state, "set"),
                         "started_rule": state_rule(group, slug, "begun", "set")
                         if "begun" in effects[group][slug] else [],
                         "detection": "exacte"})
            output.append(item)
        return output

    dlc_main_quest_names = set(catalog["canonical"]["dlc_main_quests"])
    catalog["main_quests"] = build_effect_items(
        "mainquests", catalog["canonical"]["main_quests"] + catalog["canonical"]["dlc_main_quests"],
        lambda x: x,
    )
    for quest in catalog["main_quests"]:
        quest["dlc"] = quest["name"] in dlc_main_quest_names
    quest_names = sorted({s["quest"] for s in catalog["shrines"] if s.get("quest")})
    catalog["shrine_quests"] = build_effect_items("shrinequests", quest_names, lambda x: x)
    shrine_by_quest = {s["quest"]: s for s in catalog["shrines"] if s.get("quest")}
    for quest in catalog["shrine_quests"]:
        shrine = shrine_by_quest.get(quest["name"])
        if shrine:
            quest.update({"region": shrine.get("region"), "x": shrine.get("x"),
                          "z": shrine.get("z"), "sanctuaire": shrine.get("name")})

    # Le titre officiel QuestMsg donne directement l'identifiant du journal.
    # Les offsets du mapper restent utiles pour l'état "commencé", mais ils
    # varient selon certaines versions et ne doivent pas décider de la fin.
    quest_ids = {}
    for path in args.questmsg.glob("QL_*.xmsbt"):
        text = path.read_text()
        match = re.search(r'<entry label="[^"]+_Name">\s*<text>(.*?)</text>', text, re.S)
        if match:
            title = html.unescape(re.sub(r"<.*?>", "", match.group(1))).strip()
            quest_ids[norm(title)] = path.stem.removeprefix("QL_")

    known_flag_names = set(hash_names.values())

    def journal_finish_rule(title: str) -> list[dict]:
        internal = quest_ids[norm(title)]
        candidates = [f"{internal}_Finish", f"{internal}_Finished", f"{internal}_Finish_Finished"]
        matches = [candidate for candidate in candidates if candidate in known_flag_names]
        if len(matches) != 1:
            raise RuntimeError(f"Flag de quête ambigu pour {title}: {matches}")
        return [{"flag": matches[0], "value": True}]

    for group in (catalog["main_quests"], catalog["shrine_quests"]):
        for quest in group:
            quest["rule"] = journal_finish_rule(quest["name"])
            quest["detection"] = "flag exact du journal"

    memory_lookup = {norm(name): name for name in catalog["canonical"]["memories"]}
    dlc_memory_names = {
        "championdaruk": "EX Souvenir de Daruk", "championmipha": "EX Souvenir de Mipha",
        "championrevali": "EX Souvenir de Revali", "championurbosa": "EX Souvenir d'Urbosa",
        "thechampionsballad": "EX La Ballade des Prodiges",
    }
    memories = []
    for slug, node in effects["memories"].items():
        name = memory_lookup.get(slug, dlc_memory_names.get(slug, slug))
        memories.append({"id": slug, "name": name, "dlc": slug in dlc_memory_names,
                         "rule": entries(node["remembered"]), "detection": "exacte"})
    catalog["memories"] = memories

    # Restaure les vrais noms, régions et coordonnées des 16 sanctuaires DLC.
    checklist = json.loads(args.checklist.read_text())
    shrine_metadata = checklist["shrines"]
    metadata = {norm(s["name"].replace(" Shrine", "")): s for s in shrine_metadata}
    dungeon_markers = {m["MessageID"]: m for m in json.loads(args.objmap.read_text())["markers"]["Dungeon"]}
    by_id = {s["id"]: s for s in catalog["shrines"]}
    for slug, node in effects["shrines"].items():
        meta = metadata.get(slug)
        if not meta:
            continue
        clear_flags = [r["flag"] for r in entries(node.get("complete", {})) if r["flag"].startswith("Clear_Dungeon")]
        if not clear_flags:
            continue
        dungeon_id = clear_flags[-1].removeprefix("Clear_")
        item = by_id[dungeon_id]
        item.update(meta)
        item["name"] = meta["name"]
        marker = dungeon_markers.get(dungeon_id)
        if marker:
            pos = marker["Translate"]
            item.update({"x": pos["X"], "z": pos["Z"]})
    catalog["shrine_chests"] = [
        {**s, "flag": f"CompleteTreasure_{s['id']}", "name": f"Coffre - {s['name']}"}
        for s in catalog["shrines"]
    ]

    # Quêtes secondaires : le nom affiché dans QuestMsg fournit une jointure
    # exacte vers l'identifiant interne, donc aucun rapprochement approximatif.
    side = []
    for quest in catalog["canonical"]["side_quests"]:
        side.append({**quest, "id": norm(quest["name"]), "dlc": quest.get("region") is None,
                     "rule": journal_finish_rule(quest["name"]),
                     "detection": "flag exact du journal"})
    catalog["side_quests"] = side

    # Le nom interne des 394 flags du compendium correspond sans ambiguïté au
    # nom anglais canonique. On distribue le lien, pas la base tierce brute.
    actor_names = json.loads(args.names.read_text())
    comp_by_name = {norm(item["name"]): item for item in catalog["canonical"]["compendium"]}
    compendium = []
    for flag in sorted(n for n in hash_names.values() if n.startswith("IsRegisteredPictureBook_")):
        actor = flag.removeprefix("IsRegisteredPictureBook_")
        display = actor_names.get(actor, actor)
        meta = comp_by_name.get(norm(display))
        if meta:
            compendium.append({**meta, "id": actor, "flag": flag, "detection": "exacte"})
    if len(compendium) != 394:
        raise RuntimeError(f"Compendium incomplet : {len(compendium)}/394")
    catalog["compendium"] = sorted(compendium, key=lambda x: x["dlc_master_number"])

    world_chests, dungeon_chests = [], []
    known_flags = set(hash_names.values())
    for chest_file in args.chests:
        for raw in json.loads(chest_file.read_text()):
            prefix = raw["map_type"]
            flag = f"{prefix}_{raw['name']}_{raw['hash_id']}"
            if flag not in known_flags:
                continue
            drop = raw.get("drop") or []
            drop_id = drop[1] if len(drop) > 1 else None
            drop_name = actor_names.get(drop_id, drop_id) if drop_id else "contenu variable"
            is_final_trial = prefix == "MainFieldDungeon" and raw.get("map_name") == "FinalTrial"
            item = {
                "id": f"{prefix}-{raw['hash_id']}", "hash": raw["hash_id"], "flag": flag,
                "name": f"Coffre - {drop_name}", "contenu": drop_name,
                "acteur": raw["name"], "secteur": raw.get("map_name"),
                "dlc": prefix == "AocField" or is_final_trial,
                "detection": "exacte",
            }
            if prefix == "AocField":
                item["region"] = "Trial of the Sword"
            # Les coordonnées AocField appartiennent aux salles instanciées
            # des Épreuves de l'Épée et ne doivent pas être projetées sur
            # la carte extérieure d'Hyrule.
            if prefix == "MainField" and raw.get("pos"):
                item.update({"x": raw["pos"][0], "z": raw["pos"][2]})
            (dungeon_chests if prefix == "MainFieldDungeon" else world_chests).append(item)
    catalog["world_chests"] = world_chests
    catalog["dungeon_chests"] = dungeon_chests

    armor_by_name = {}
    for actor, display in actor_names.items():
        if re.match(r"Armor_\d+_(Head|Upper|Lower)$", actor):
            armor_by_name.setdefault(norm(display), []).append(actor)
    armor_owned = []
    for armor in catalog["canonical"]["enhanceable_armor"]:
        variants = armor_by_name[norm(armor["name"])]
        base_actor = min(variants, key=lambda actor: int(actor.split("_")[1]))
        armor_owned.append({**armor, "id": base_actor, "flag": f"IsGet_{base_actor}",
                            "name": armor["name"], "detection": "possession exacte"})
    catalog["armor_owned"] = armor_owned

    waypoint_text = args.waypoint_map.read_text()
    waypoint_re = re.compile(
        r'"internal_name":"([^"]+)",\s*"display_name":"([^"]+)",\s*'
        r'"x":(-?[0-9.]+),\s*"y":(-?[0-9.]+)'
    )
    official_locations = [
        {"flag": flag, "name": name, "x": float(x), "z": float(z),
         "type": "créature divine" if flag.startswith("Location_Remains") else
                 "tour" if flag.startswith("Location_MapTower") else "lieu"}
        for flag, name, x, z in waypoint_re.findall(waypoint_text)
    ]
    if len(official_locations) != 187:
        raise RuntimeError(f"Marqueurs officiels incomplets : {len(official_locations)}/187")
    catalog["official_map_locations"] = official_locations

    # Ces trois marqueurs comptent dans la carte officielle, mais la source
    # historique de la catégorie `locations` ne les exposait pas.
    extra_location_regions = {
        "Location_AncientLabo": "Akkala",
        "Location_HatenoLabo": "Hateno",
        "Location_StartPoint": "Great Plateau",
    }
    known_location_flags = {item["flag"] for item in catalog["locations"]}
    for marker in official_locations:
        if marker["flag"] in extra_location_regions and marker["flag"] not in known_location_flags:
            catalog["locations"].append({
                **marker,
                "region": extra_location_regions[marker["flag"]],
                "dlc": False,
                "detection": "exacte",
            })

    # Activités utiles qui ne disposent pas toutes d'un flag simple et stable.
    catalog["manual"] = {
        "ameliorations_armures": [{**a, "status": "manuel"} for a in catalog["canonical"]["enhanceable_armor"]],
        "chiens": [{**d, "status": "manuel"} for d in catalog["canonical"]["dogs"]],
    }
    catalog["schema_version"] = 2
    args.catalog.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")))
    print({k: len(catalog[k]) for k in ("shrines", "main_quests", "shrine_quests", "side_quests", "memories", "compendium", "world_chests", "dungeon_chests", "armor_owned", "official_map_locations")})


if __name__ == "__main__":
    main()