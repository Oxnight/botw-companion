#!/usr/bin/env python3
"""Construit les variantes d'armures et leurs recettes dans catalog.json.

Les identifiants de variantes viennent du Savegame Editor de Marc Robledo.
Les recettes viennent du BOTW Armor Upgrade Tracker de Jared Wilcurt.
Ce script de développement n'est pas distribué comme dépendance d'exécution.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import unicodedata


ARMOR_ALIASES = {
    "Barbarian Leg Wraps": "Barbarian Wraps",
    "Fierce Deity Mask": "Fierce Deity's Mask",
    "Fierce Deity Armor": "Fierce Deity's Armor",
    "Fierce Deity Boots": "Fierce Deity's Boots",
    "Cap of the Wind": "Cap of Wind",
    "Tunic of the Wind": "Tunic of Wind",
    "Trousers of the Wind": "Trousers of Wind",
}

# Plusieurs noms d'acteurs désignent le même objet visible dans le monde.
# Cette table choisit l'acteur réellement stocké dans l'inventaire.
MATERIAL_ACTORS = {
    "Acorn": "Item_Fruit_K",
    "Blue Nightshade": "Item_PlantGet_I",
    "Courser Bee Honey": "Obj_BeeHome_A",
    "Energetic Rhino Beetle": "Animal_Insect_AA",
    "Hearty Bass": "Item_FishGet_B",
    "Hyrule Bass": "Item_FishGet_A",
    "Octo Balloon": "Item_Enemy_57",
    "Rushroom": "Item_MushroomGet_D",
    "Silent Princess": "Item_PlantGet_J",
    "Silent Shroom": "Item_Mushroom_J",
    "Sneaky River Snail": "Item_FishGet_M",
    "Stealthfin Trout": "Item_FishGet_X",
    "Sunset Firefly": "Animal_Insect_E",
    "Sunshroom": "Item_Mushroom_C",
    "Swift Carrot": "Item_PlantGet_M",
    "Swift Violet": "Item_PlantGet_O",
    "Voltfruit": "Item_Fruit_C",
    "Warm Safflina": "Item_PlantGet_F",
    "Zapshroom": "Item_Mushroom_H",
}


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", value.lower())


def extract_armor_array(source: str) -> list[dict]:
    start = source.index("armors: [") + len("armors: ")
    depth = 0
    in_string = escaped = False
    for index in range(start, len(source)):
        char = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return json.loads(source[start:index + 1])
    raise ValueError("Tableau armors introuvable ou incomplet")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--editor-data", type=Path, required=True)
    parser.add_argument("--recipes", type=Path, required=True)
    parser.add_argument("--names", type=Path, required=True)
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text())
    editor = args.editor_data.read_text()
    tracker = extract_armor_array(args.recipes.read_text())
    recipes = {entry["name"]: entry["ingredients"] for entry in tracker}
    actor_names = json.loads(args.names.read_text())

    variants_by_name: dict[str, dict[int, str]] = {}
    pattern = re.compile(r'(Armor_\d{3}_(?:Head|Upper|Lower)):"([^"]+)"')
    for actor, display in pattern.findall(editor):
        level = display.count("★")
        name = display.replace(" ★★★★", "").replace(" ★★★", "").replace(" ★★", "").replace(" ★", "")
        variants_by_name.setdefault(name, {})[level] = actor

    by_display: dict[str, list[str]] = {}
    for actor, display in actor_names.items():
        by_display.setdefault(norm(display), []).append(actor)

    def material_actor(name: str) -> str:
        if name in MATERIAL_ACTORS:
            return MATERIAL_ACTORS[name]
        candidates = [actor for actor in by_display.get(norm(name), []) if not actor.startswith("Armor_")]
        if len(candidates) != 1:
            raise RuntimeError(f"Acteur de matériau ambigu pour {name}: {candidates}")
        return candidates[0]

    output = []
    for armor in catalog["armor_owned"]:
        editor_name = ARMOR_ALIASES.get(armor["name"], armor["name"])
        levels = variants_by_name.get(editor_name, {})
        if set(levels) != set(range(5)):
            raise RuntimeError(f"Variantes incomplètes pour {armor['name']}: {levels}")
        recipe = recipes[armor["name"]]
        enriched_recipe = {
            str(level): [
                {**material, "id": material_actor(material["name"])}
                for material in recipe[str(level)]
            ]
            for level in range(1, 5)
        }
        output.append({
            **armor,
            "id": levels[0],
            "flag": f"IsGet_{levels[0]}",
            "variants": [levels[level] for level in range(5)],
            "recettes": enriched_recipe,
            "detection": "inventaire exact et niveau 0 à 4 étoiles",
        })

    catalog["armor_owned"] = output
    catalog.get("manual", {}).pop("ameliorations_armures", None)
    catalog["schema_version"] = 3
    args.catalog.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")))
    print(f"Armures enrichies : {len(output)}; recettes : {sum(bool(x['recettes']) for x in output)}")


if __name__ == "__main__":
    main()