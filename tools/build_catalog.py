#!/usr/bin/env python3
"""Construit les données distribuées depuis les dépôts tiers documentés."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


ENTRY_RE = re.compile(
    r"0x([0-9a-f]+):\s*\{\"internal_name\":\"([^\"]+)\",\s*"
    r"\"display_name\":\"([^\"]+)\",\s*\"x\":(-?[0-9.]+),\s*\"y\":(-?[0-9.]+)\}",
    re.I,
)


def section(text: str, name: str) -> list[dict]:
    match = re.search(rf"var {name} = \{{(.*?)\n    \}};", text, re.S)
    if not match:
        raise ValueError(f"Section {name} absente")
    return [
        {"hash": int(h, 16), "flag": internal, "name": display, "x": float(x), "z": float(z)}
        for h, internal, display, x, z in ENTRY_RE.findall(match.group(1))
    ]


def js_array(text: str, name: str) -> list[int]:
    match = re.search(rf"{name}:\[(.*?)\]", text, re.S)
    if not match:
        raise ValueError(f"Tableau {name} absent")
    return [int(value, 16) for value in re.findall(r"0x([0-9a-f]+)", match.group(1), re.I)]


def coordinates(text: str) -> dict[int, tuple[float, float]]:
    return {
        int(h, 16): (float(x), float(z))
        for h, x, _height, z in re.findall(
            r"0x([0-9a-f]+):\[(-?[0-9.eE]+),(-?[0-9.eE]+),(-?[0-9.eE]+)\]", text
        )
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--editor", type=Path, required=True)
    parser.add_argument("--viewer", type=Path, required=True)
    parser.add_argument("--checklist", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    hashes = {}
    names_by_hash = {}
    for line in (args.editor / "zelda-botw.hashes.csv").read_text().splitlines():
        hash_id, type_id, name = line.split(";", 2)
        hashes[hash_id] = [int(type_id), name]
        names_by_hash[int(hash_id)] = name
    (args.output / "hashes.json").write_text(json.dumps(hashes, separators=(",", ":")))

    map_text = (args.viewer / "assets/js/map-locations.js").read_text()
    data_text = (args.editor / "zelda-botw.data.js").read_text()
    coord_text = (args.editor / "zelda-botw.locations.js").read_text()
    checklist = json.loads(args.checklist.read_text())
    coords = coordinates(coord_text)

    warps = section(map_text, "warps")
    shrines = [item for item in warps if item["flag"].startswith("Location_Dungeon")]
    towers = [item for item in warps if item["flag"].startswith("Location_MapTower")]
    metadata = {item["name"]: item for item in checklist["shrines"]}
    for item in shrines:
        internal = item["flag"].removeprefix("Location_Dungeon")
        item["id"] = f"Dungeon{internal}"
        item["flag"] = f"Clear_Dungeon{internal}"
        item.update({k: v for k, v in metadata.get(item["name"], {}).items() if k != "name"})
    for number in range(120, 136):
        shrines.append({
            "id": f"Dungeon{number}", "flag": f"Clear_Dungeon{number}",
            "name": f"Sanctuaire DLC Dungeon{number}", "dlc": True,
        })
    shrine_chests = [
        {**item, "flag": f"CompleteTreasure_{item['id']}", "name": f"Coffre - {item['name']}"}
        for item in shrines
    ]

    def bosses(array: str, label: str) -> list[dict]:
        result = []
        for index, hash_id in enumerate(js_array(data_text, array), 1):
            xz = coords.get(hash_id)
            item = {"id": f"{label.lower()}-{index:02}", "name": f"{label} {index:02}", "hash": hash_id,
                    "flag": names_by_hash.get(hash_id, f"hash:{hash_id}")}
            if xz:
                item.update({"x": xz[0], "z": xz[1]})
            result.append(item)
        return result

    catalog = {
        "schema_version": 1,
        "shrines": shrines,
        "shrine_chests": shrine_chests,
        "koroks": section(map_text, "koroks"),
        "towers": towers,
        "locations": section(map_text, "locations"),
        "hinoxes": bosses("DEFEATED_HINOX", "Hinox"),
        "taluses": bosses("DEFEATED_TALUS", "Talus"),
        "moldugas": bosses("DEFEATED_MOLDUGA", "Moldarquor"),
        "canonical": {key: checklist[key] for key in (
            "main_quests", "dlc_main_quests", "memories", "side_quests", "other",
            "compendium", "dogs", "enhanceable_armor",
        )},
    }
    (args.output / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")))
    print({key: len(value) for key, value in catalog.items() if isinstance(value, list)})


if __name__ == "__main__":
    main()