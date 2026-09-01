#!/usr/bin/env python3
"""Ajoute les points géographiques des quêtes et souvenirs au catalogue.

Les marqueurs Zelda Dungeon utilisent une carte de 24 000 pixels :
``x_botw = y_carte / 2`` et ``z_botw = -x_carte / 2``.  Le script conserve
séparément le départ, les objectifs intermédiaires et la destination afin de
ne jamais présenter un sanctuaire comme le donneur d'une quête.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import unicodedata


ZD_SOURCE = "Zelda Dungeon Interactive Map"
ZD_URL = "https://www.zeldadungeon.net/breath-of-the-wild-interactive-map/"
BOTW_TOOLS_SOURCE = "botw-tools - données internes du jeu"
BOTW_TOOLS_URL = "https://github.com/MrCheeze/botw-tools"
PLACE_ALIASES = {
    "UMiiVillageShopYadoya": "Tarrey Town - auberge",
    "UMiiVillageShopYorozu": "Tarrey Town - magasin général",
}


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = value.lower()
    return re.sub(r"[^a-z0-9]", "", value)


def game_coords(coords: list[float]) -> tuple[float, float]:
    """Convertit [x, y] de la carte ZD en [x, z] du monde BOTW."""
    return round(coords[1] / 2, 3), round(-coords[0] / 2, 3)


def markers(data: list[dict], category: str) -> list[dict]:
    return [
        marker
        for group in data
        if group.get("name") == category
        for layer in group.get("layers", [])
        for marker in layer.get("markers", [])
    ]


def nearby(point: tuple[float, float], places: list[dict]) -> tuple[str | None, float | None]:
    if not places:
        return None, None
    x, z = point
    place = min(places, key=lambda p: (p["x"] - x) ** 2 + (p["z"] - z) ** 2)
    distance = math.hypot(place["x"] - x, place["z"] - z)
    if distance > 600:
        return None, None
    return PLACE_ALIASES.get(place["name"], place["name"]), round(distance)


def make_point(
    coords: tuple[float, float], role: str, label: str, places: list[dict],
    *, source: str = ZD_SOURCE, source_url: str = ZD_URL, source_id: str | None = None,
) -> dict:
    place, distance = nearby(coords, places)
    point = {
        "role": role,
        "label": label,
        "x": coords[0],
        "z": coords[1],
        "source": source,
        "source_url": source_url,
    }
    if source_id:
        point["source_id"] = source_id
    if place:
        point["nearby"] = place
        point["nearby_distance_m"] = distance
    return point


def marker_index(data: list[dict], category: str) -> dict[str, dict]:
    return {norm(marker["name"]): marker for marker in markers(data, category)}


def objective_label(marker: dict) -> str:
    fragment = marker.get("link", "").partition("#")[2]
    numbered = re.fullmatch(r"Objective\s+(\d+)", fragment)
    if numbered:
        return f"Objectif {numbered.group(1)}"
    if fragment and fragment != "Objective":
        return f"Objectif - {fragment}"
    suffix = re.search(r"Objective\s+(\d+)$", marker.get("id", ""))
    return f"Objectif {suffix.group(1)}" if suffix else "Objectif"


def memory_title(marker: dict) -> str:
    title = re.sub(r"^(?:EX )?Recovered Memory #\d+\s+-\s+", "", marker["name"])
    return re.sub(r"\s+\(Picture \d+\)$", "", title)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--wiki", type=Path, required=True)
    parser.add_argument("--pins", type=Path, required=True)
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text())
    wiki = json.loads(args.wiki.read_text())
    pins = json.loads(args.pins.read_text())
    places = catalog["official_map_locations"]

    category_specs = (
        ("main_quests", "Main Quest"),
        ("shrine_quests", "Shrine Quest"),
        ("side_quests", "Side Quest"),
    )
    for catalog_key, zd_category in category_specs:
        index = marker_index(wiki, zd_category)
        for quest in catalog[catalog_key]:
            key = norm(quest["name"])
            marker = index.get(key)
            if not marker and key == norm("EX The Champions' Ballad"):
                marker = index.get(norm("EX Champions' Ballad"))
            if not marker and quest["name"] != "[Xenoblade Chronicles 2]":
                raise RuntimeError(f"Marqueur {zd_category} introuvable : {quest['name']}")
            if marker:
                start = make_point(
                    game_coords(marker["coords"]), "depart", "Départ de la quête", places,
                    source_id=marker.get("id"),
                )
                quest["geo_points"] = [start]
                quest.update({"x": start["x"], "z": start["z"],
                              "location_role": "depart", "nearby": start.get("nearby")})

    objectives_by_name: dict[str, list[dict]] = {}
    for marker in markers(wiki, "Quest Objective"):
        objective_name = marker["name"]
        if objective_name == "Obtain the Master Sword":
            objective_name = "The Hero's Sword"
        objectives_by_name.setdefault(norm(objective_name), []).append(marker)
    for group in (catalog["main_quests"], catalog["shrine_quests"], catalog["side_quests"]):
        for quest in group:
            for marker in objectives_by_name.get(norm(quest["name"]), []):
                quest.setdefault("geo_points", []).append(make_point(
                    game_coords(marker["coords"]), "objectif", objective_label(marker), places,
                    source_id=marker.get("id"),
                ))

    # Les anciennes coordonnées des quêtes de sanctuaire désignaient le
    # sanctuaire final. Elles deviennent désormais une destination explicite.
    shrines_by_name = {shrine["name"]: shrine for shrine in catalog["shrines"]}
    for quest in catalog["shrine_quests"]:
        shrine = shrines_by_name[quest["sanctuaire"]]
        quest["geo_points"].append(make_point(
            (round(shrine["x"], 3), round(shrine["z"], 3)), "destination",
            f"Sanctuaire - {shrine['name']}", places,
            source="ObjMap / données internes du jeu",
            source_url="https://objmap.zeldamods.org/",
            source_id=shrine["id"],
        ))

    # Le crossover est commandé automatiquement et ne possède pas de donneur.
    # Ces trois zones sont les CollaboShootingStarArea de la carte statique.
    xenoblade = next(q for q in catalog["side_quests"] if q["name"] == "[Xenoblade Chronicles 2]")
    xenoblade_specs = (
        ((-44.0, 2496.0), "Indice 1 - ciel austral depuis le milieu du plus grand pont", "E-7"),
        ((3321.0, -3429.0), "Indice 2 - ciel oriental depuis l’œil gauche du crâne", "I-1"),
        ((-2783.556, -2895.5), "Indice 3 - ciel du sud-est depuis la haute montagne enneigée percée", "C-2"),
    )
    xenoblade["geo_points"] = [
        make_point(coords, "objectif", label, places, source=BOTW_TOOLS_SOURCE,
                   source_url=BOTW_TOOLS_URL, source_id=f"{section}_Static")
        for coords, label, section in xenoblade_specs
    ]
    first = xenoblade["geo_points"][0]
    xenoblade.update({"x": first["x"], "z": first["z"], "location_role": "objectif",
                      "nearby": first.get("nearby")})

    memory_index = {norm(memory_title(marker)): marker for marker in markers(pins, "Memory")}
    for memory in catalog["memories"]:
        marker = memory_index.get(norm(memory["name"])) or memory_index.get(norm(memory["id"]))
        if not marker:
            raise RuntimeError(f"Souvenir introuvable : {memory['name']}")
        title = memory_title(marker)
        if marker.get("tags") == ["DLC"]:
            memory["name"] = f"EX {title}"
            memory["dlc"] = True
        point = make_point(game_coords(marker["coords"]), "souvenir", "Lieu du souvenir", places,
                           source_id=marker.get("id"))
        memory["geo_points"] = [point]
        memory.update({"x": point["x"], "z": point["z"], "location_role": "souvenir",
                       "nearby": point.get("nearby")})

    catalog["schema_version"] = 4
    args.catalog.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")

    expected_primary = sum(len(catalog[key]) for key in ("main_quests", "shrine_quests", "side_quests", "memories"))
    actual_primary = sum(
        item.get("x") is not None and item.get("z") is not None
        for key in ("main_quests", "shrine_quests", "side_quests", "memories")
        for item in catalog[key]
    )
    point_count = sum(
        len(item.get("geo_points", []))
        for key in ("main_quests", "shrine_quests", "side_quests", "memories")
        for item in catalog[key]
    )
    if actual_primary != expected_primary:
        raise RuntimeError(f"Couverture géographique incomplète : {actual_primary}/{expected_primary}")
    print(f"{actual_primary}/{expected_primary} éléments localisés ; {point_count} points structurés")


if __name__ == "__main__":
    main()