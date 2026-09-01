#!/usr/bin/env python3
"""Construit la référence cartographique intérieure depuis les placements BOTW extraits."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


CHEST_ACTORS = {
    "TBox_Dungeon_Stone", "TBox_Dungeon_Iron",
    "TBox_Field_Stone", "TBox_Field_Iron",
}
MAP_LABELS = {
    "RemainsElectric": "Créature divine Vah'Naboris",
    "RemainsFire": "Créature divine Vah'Rudania",
    "RemainsWater": "Créature divine Vah'Ruta",
    "RemainsWind": "Créature divine Vah'Medoh",
    "FinalTrial": "Épreuve finale de l'Ode aux Prodiges",
}


def instance_from_file(path: Path) -> str:
    return path.stem.split("_Static", 1)[0].split("_Dynamic", 1)[0]


def parse_chests(directory: Path, names: dict[str, str]) -> dict[str, list[dict]]:
    result: dict[str, dict[int, dict]] = defaultdict(dict)
    for path in sorted(directory.glob("*.xml")):
        if "NoGrudgeMerge" in path.name:
            continue
        instance = instance_from_file(path)
        root = ET.parse(path).getroot()
        for value in root.iter("value"):
            unit = value.findtext("UnitConfigName")
            if not unit or not unit.startswith("TBox_"):
                continue
            raw_hash = value.attrib.get("HashId")
            translate = value.find("Translate")
            if raw_hash is None or translate is None:
                continue
            coords = [float(node.text.rstrip("f")) for node in translate.findall("value")]
            if len(coords) != 3:
                continue
            drop = value.findtext("./_Parameters/DropActor") or ""
            hash_id = int(raw_hash) & 0xFFFFFFFF
            result[instance].setdefault(hash_id, {
                "hash": hash_id, "actor": drop,
                "content": names.get(drop, drop or "Contenu déterminé par le jeu"),
                "x": round(coords[0], 2), "y": round(coords[1], 2),
                "z": round(coords[2], 2),
            })
    return {key: sorted(values.values(), key=lambda item: item["hash"])
            for key, values in result.items()}


def bounds(points: list[dict]) -> dict:
    return {
        "min_x": min(point["x"] for point in points),
        "max_x": max(point["x"] for point in points),
        "min_z": min(point["z"] for point in points),
        "max_z": max(point["z"] for point in points),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--botw-tools", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text())
    names = json.loads((args.botw_tools / "botw_names.json").read_text())
    dungeon = parse_chests(args.botw_tools / "mubin_dungeon", names)
    trial = parse_chests(args.botw_tools / "mubin_trial", names)

    shrine_names = {item["id"]: item["name"] for item in catalog["shrines"]}
    shrines = {}
    for number in range(136):
        map_id = f"Dungeon{number:03d}"
        points = dungeon.get(map_id, [])
        if not points:
            raise SystemExit(f"Aucun coffre trouvé dans {map_id}")
        shrines[map_id] = {
            "map_context": "shrine_interior", "interior_map": map_id,
            "interior_map_label": f"Intérieur - {shrine_names[map_id]}",
            "chest_count": len(points), "interior_bounds": bounds(points),
            "interior_chests": points,
        }

    trial_by_hash = {}
    for map_id, points in trial.items():
        for point in points:
            trial_by_hash[str(point["hash"])] = {
                "map_context": "trial_interior", "interior_map": f"AocField/{map_id}",
                "interior_map_label": f"Épreuves de l'Épée - section {map_id}",
                "interior_bounds": bounds(points), "interior_position": point,
            }

    dungeon_by_hash = {}
    for map_id in MAP_LABELS:
        points = dungeon.get(map_id, [])
        for point in points:
            dungeon_by_hash[str(point["hash"])] = {
                "map_context": "dungeon_interior", "interior_map": map_id,
                "interior_map_label": MAP_LABELS[map_id],
                "interior_bounds": bounds(points), "interior_position": point,
            }

    expected_trial = {str(item["hash"]) for item in catalog["world_chests"]
                      if item.get("region") == "Trial of the Sword"}
    expected_dungeon = {str(item["hash"]) for item in catalog["dungeon_chests"]}
    if expected_trial != set(trial_by_hash):
        raise SystemExit("La liste des 49 coffres des Épreuves ne correspond pas au catalogue")
    if expected_dungeon != set(dungeon_by_hash):
        raise SystemExit("La liste des 42 coffres de donjon ne correspond pas au catalogue")

    output = {
        "schema_version": 1,
        "sources": [
            {"name": "MrCheeze/botw-tools - placements MUBIN extraits du jeu",
             "url": "https://github.com/MrCheeze/botw-tools"},
            {"name": "ZeldaMods Dungeon pack - contexte des cartes intérieures",
             "url": "https://zeldamods.org/wiki/Dungeon_pack"},
            {"name": "BOTW Object Map - contrôle interactif des acteurs et coffres",
             "url": "https://objmap.zeldamods.org/"},
        ],
        "audit": {
            "shrine_completion_entries": len(shrines),
            "physical_shrine_chests": sum(item["chest_count"] for item in shrines.values()),
            "trial_chests": len(trial_by_hash), "dungeon_chests": len(dungeon_by_hash),
        },
        "shrines": shrines, "trial_chests": trial_by_hash,
        "dungeon_chests": dungeon_by_hash,
    }
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()