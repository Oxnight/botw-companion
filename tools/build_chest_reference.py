#!/usr/bin/env python3
"""Construit la référence hors ligne des accès aux coffres de BOTW.

Les relations d'acteurs viennent de l'API d'ObjMap. Les formulations françaises
sont originales et décrivent uniquement ce que les données permettent de
prouver : accès individuel lorsqu'un paramètre ou un groupe le révèle, méthode
par famille dans les autres cas.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

OBJ_API = "https://radar.zeldamods.org/obj/{map_type}/{map_name}/{hash_id}"

SOURCES = [
    {"name": "BOTW Object Map", "url": "https://objmap.zeldamods.org/"},
    {"name": "Code source de BOTW Object Map", "url": "https://github.com/zeldamods/objmap"},
    {"name": "Zelda Dungeon - Treasure Chest", "url": "https://www.zeldadungeon.net/wiki/Treasure_Chest"},
    {"name": "Zelda Dungeon - sanctuaires BOTW", "url": "https://www.zeldadungeon.net/breath-of-the-wild-walkthrough/shrine-locations/"},
    {"name": "Zelda Dungeon - parcours BOTW", "url": "https://www.zeldadungeon.net/breath-of-the-wild-walkthrough/"},
]

WORLD_METHODS = {
    "buried": {
        "label": "Coffre enfoui - accès individuel confirmé",
        "quality": 3,
        "requirements": ["Polaris"],
        "steps": [
            "Active Polaris autour du point exact pour faire ressortir le coffre sous le sol.",
            "Saisis-le avec Polaris et dépose-le sur une surface stable.",
            "Ouvre-le et sauvegarde afin d'enregistrer son flag permanent.",
        ],
    },
    "burn_ivy": {
        "label": "Lierre inflammable - accès individuel confirmé",
        "quality": 3,
        "requirements": ["Une flamme ou une flèche de feu"],
        "steps": [
            "Repère le lierre qui bloque le coffre au point indiqué.",
            "Brûle le lierre en restant à distance de la propagation du feu.",
            "Attends que le passage soit dégagé, puis ouvre le coffre.",
        ],
    },
    "enemy_locked": {
        "label": "Camp ennemi - verrou individuel confirmé",
        "quality": 3,
        "requirements": ["Équipement adapté aux ennemis du secteur"],
        "steps": [
            "Élimine tous les ennemis appartenant au camp autour du coffre.",
            "Vérifie le signal sonore et le changement de couleur du coffre verrouillé.",
            "Ouvre le coffre désormais déverrouillé et sauvegarde.",
        ],
    },
    "flying_platform": {
        "label": "Plateforme volante à Octos - accès individuel confirmé",
        "quality": 3,
        "requirements": ["Arc et flèches", "Paravoile recommandée"],
        "steps": [
            "Observe la plateforme soutenue par les Octos aériens au-dessus du point indiqué.",
            "Atteins la plateforme ou abats progressivement les Octos pour contrôler sa descente.",
            "Stabilise-toi sur la plateforme, puis ouvre le coffre avant qu'elle ne dérive.",
        ],
    },
    "rock_cover": {
        "label": "Dalle rocheuse - obstacle individuel confirmé",
        "quality": 3,
        "requirements": ["Cinetis, ballon octo ou levier physique selon la dalle"],
        "steps": [
            "Repère la dalle ou le rocher posé directement sur l'accès au coffre.",
            "Déplace l'obstacle avec Cinetis, un ballon octo ou un impact adapté.",
            "Approche-toi de l'ouverture dégagée et récupère le coffre.",
        ],
    },
    "event_locked": {
        "label": "Déclencheur local - liaison confirmée",
        "quality": 2,
        "requirements": ["Observer les interrupteurs et acteurs proches"],
        "steps": [
            "Rejoins le point exact et identifie le mécanisme ou l'événement associé au coffre.",
            "Active le déclencheur local jusqu'à ce que le coffre devienne accessible.",
            "Ouvre le coffre ; la liaison est confirmée, mais la séquence précise dépend du lieu.",
        ],
    },
    "metal": {
        "label": "Coffre métallique - méthode de famille vérifiée",
        "quality": 2,
        "requirements": ["Polaris recommandé"],
        "steps": [
            "Rejoins les coordonnées et active Polaris pour repérer le coffre métallique.",
            "S'il est immergé, enfoncé ou hors d'atteinte, saisis-le avec Polaris et ramène-le sur une surface stable.",
            "Ouvre-le et vérifie son passage en statut terminé.",
        ],
    },
    "stone": {
        "label": "Coffre en pierre - méthode de famille vérifiée",
        "quality": 2,
        "requirements": ["Accès physique au point indiqué"],
        "steps": [
            "Rejoins les coordonnées et cherche un passage physique jusqu'au coffre en pierre.",
            "Ce coffre fixe ne se déplace pas avec Polaris : inspecte les hauteurs, cavités et obstacles voisins.",
            "Place-toi devant le coffre et ouvre-le normalement.",
        ],
    },
    "wood": {
        "label": "Coffre en bois - méthode de famille vérifiée",
        "quality": 2,
        "requirements": ["Accès physique ; bombe ou arme possible"],
        "steps": [
            "Rejoins les coordonnées et localise le coffre en bois.",
            "Ouvre-le normalement ; s'il est inaccessible, le bois peut être brisé ou brûlé pour libérer son contenu.",
            "Ramasse le contenu et vérifie l'enregistrement de l'ouverture.",
        ],
    },
    "trial_room": {
        "label": "Salle des Épreuves de l'Épée - méthode vérifiée",
        "quality": 2,
        "requirements": ["DLC 1 et niveau correspondant des Épreuves de l'Épée"],
        "steps": [
            "Entre dans la salle correspondant au secteur intérieur indiqué.",
            "Sécurise la salle puis fouille les plateformes, arbres, caisses et recoins avant de continuer.",
            "Ouvre le coffre pendant cette tentative : le matériel de l'épreuve n'est pas conservé après la sortie.",
        ],
    },
}

SHRINE_RULES = [
    (("feu", "flamme", "fondre"), "Feu et obstacles inflammables", "Utilise une flamme, une torche ou une flèche de feu pour dégager l'accès au coffre."),
    (("électricité", "électrique", "circuit", "cinq de fer"), "Circuit électrique", "Relie les conducteurs métalliques avec Polaris jusqu'à alimenter la grille ou la plateforme du coffre."),
    (("vent", "envol", "cieux", "paravoile"), "Courants ascendants", "Prends de la hauteur dans le courant puis dirige la paravoile vers la plateforme latérale du coffre."),
    (("eau", "glace", "flot"), "Cryonis et eau", "Crée ou détruis les piliers Cryonis nécessaires pour atteindre ou soulever le coffre."),
    (("bombe", "destruction", "canon", "trajectoire"), "Bombes et trajectoire", "Réalise une trajectoire secondaire ou détruis le passage rocheux qui protège le coffre."),
    (("temps", "instant", "mouvement", "cinetis"), "Cinetis et synchronisation", "Fige le mécanisme au bon instant afin de créer la fenêtre d'accès au coffre."),
    (("aimant", "magnét", "fer", "passerelle"), "Polaris et objets métalliques", "Déplace les blocs ou le coffre avec Polaris pour former le passage jusqu'à lui."),
    (("équilibre", "poids", "balance"), "Poids et équilibre", "Répartis les objets sur les plaques ou balances, puis emprunte la position obtenue pour rejoindre le coffre."),
    (("appareil", "mécanisme", "rouage", "angle"), "Appareil gyroscopique", "Stabilise le mécanisme avec de petits mouvements, d'abord dans la position donnant accès au coffre."),
    (("force", "combat", "épreuve"), "Épreuve de force", "Remporte le combat : le coffre se trouve dans la salle libérée avant l'autel."),
]

DUNGEON_METHODS = {
    "Vah'Ruta": ("Tronc, roues hydrauliques et Cryonis", "Ajuste la trompe sur la carte, utilise Cryonis ou Polaris selon la salle et récupère le coffre avant de changer de configuration."),
    "Vah'Rudania": ("Rotation, obscurité et feu", "Fais pivoter Rudania pour transformer murs et plafonds en passages, détruis les yeux de malice et exploite les flammes ou Polaris."),
    "Vah'Medoh": ("Inclinaison, vent et paravoile", "Incline Medoh pour déplacer nacelles et plateformes, puis utilise les courants d'air et la paravoile vers le coffre."),
    "Vah'Naboris": ("Rotation des cylindres et électricité", "Aligne les trois cylindres pour créer le passage ou le circuit, puis utilise Polaris et les connexions électriques autour du coffre."),
    "Épreuve finale de l'Épée": ("Rotation et circuits de l'Épreuve finale", "Oriente les sections de l'Épreuve finale, complète le circuit ou le courant d'air local, puis rejoins le coffre dans cette configuration."),
}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _payload_catalog(path: Path) -> dict:
    payload = _read_json(path)
    return payload.get("catalog", payload)


def _fetch_json(url: str, attempts: int = 4):
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "BOTW-Companion-reference-builder/1.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt + 1 == attempts:
                raise
            time.sleep(0.5 * (attempt + 1))


def _object_key(item: dict) -> tuple[str, str, int]:
    map_type = item["id"].split("-", 1)[0]
    return map_type, item["secteur"], int(item["hash"])


def _cache_file(cache: Path, item: dict, suffix: str = "") -> Path:
    map_type, map_name, hash_id = _object_key(item)
    folder = cache / ("groups" if suffix else "full")
    return folder / f"{map_type}__{map_name}__{hash_id}.json"


def _download_one(cache: Path, item: dict) -> None:
    map_type, map_name, hash_id = _object_key(item)
    base = OBJ_API.format(map_type=map_type, map_name=map_name, hash_id=hash_id)
    for suffix in ("", "/gen_group"):
        target = _cache_file(cache, item, suffix)
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = _fetch_json(base + suffix)
        target.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _fetch_all(cache: Path, items: list[dict], workers: int) -> None:
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_download_one, cache, item): item for item in items}
        for index, future in enumerate(as_completed(futures), 1):
            future.result()
            if index % 100 == 0:
                print(f"{index}/{len(items)} objets ObjMap récupérés")


def _group_names(group: list[dict]) -> set[str]:
    return {str(actor.get("name") or actor.get("data", {}).get("UnitConfigName") or "") for actor in group}


def _classify(item: dict, obj: dict, group: list[dict]) -> str:
    params = obj.get("data", {}).get("!Parameters", {})
    names = _group_names(group)
    actor = item.get("acteur", "")
    if params.get("IsInGround") is True:
        return "buried"
    if any("AirOctarock" in name for name in names):
        return "flying_platform"
    if any("IvyBurn" in name or "Burnable" in name for name in names):
        return "burn_ivy"
    if actor == "TBox_Field_Enemy":
        return "enemy_locked"
    if any("RockCover" in name for name in names):
        return "rock_cover"
    if item["id"].startswith("AocField-"):
        return "trial_room"
    if "NoReaction" in actor:
        return "event_locked"
    if "Iron" in actor:
        return "metal"
    if "Stone" in actor:
        return "stone"
    return "wood"


def _shrine_method(trial: str) -> tuple[str, str]:
    normalized = (trial or "").casefold()
    for needles, label, access in SHRINE_RULES:
        if any(needle in normalized for needle in needles):
            return label, (
                f"Mécanique dominante de l'épreuve : {access} "
                "Rejoins d'abord le point intérieur indiqué et applique-la si l'obstacle de ce coffre y correspond."
            )
    return (
        "Détour intérieur",
        "Suis le mécanisme principal de l'épreuve, puis inspecte la plateforme ou le renfoncement correspondant aux coordonnées intérieures avant l'autel.",
    )


def build(catalog: dict, cartography: dict, cache: Path) -> dict:
    world = {}
    counts = {}
    for item in catalog["world_chests"]:
        obj = _read_json(_cache_file(cache, item))
        group = _read_json(_cache_file(cache, item, "/gen_group"))
        kind = _classify(item, obj, group)
        counts[kind] = counts.get(kind, 0) + 1
        method = WORLD_METHODS[kind]
        entry = {
            "kind": kind,
            "label": method["label"],
            "quality": method["quality"],
            "requirements": method["requirements"],
            "steps": method["steps"],
            "y": obj.get("pos", [None, None, None])[1],
            "group_actor_count": len(group),
        }
        location = obj.get("location")
        if location:
            entry["location"] = location
        world[str(item["hash"])] = entry

    dungeons = {}
    for item in catalog["dungeon_chests"]:
        base = cartography["dungeon_chests"][str(item["hash"])]
        map_name = base["interior_map"]
        label, access = DUNGEON_METHODS[map_name]
        point = base["interior_position"]
        dungeons[str(item["hash"])] = {
            "area": f"Position intérieure X {point['x']:.1f}, Y {point['y']:.1f}, Z {point['z']:.1f}",
            "access_label": label,
            "access": access,
            "quality": 2,
        }

    shrines = {}
    physical = 0
    shrine_by_id = {item["id"]: item for item in catalog["shrine_chests"]}
    for shrine_id, base in cartography["shrines"].items():
        item = shrine_by_id[shrine_id]
        label, access = _shrine_method(item.get("trial", ""))
        entries = []
        for number, point in enumerate(base["interior_chests"], 1):
            entries.append({
                "hash": point["hash"],
                "number": number,
                "area": f"Point intérieur {number}/{base['chest_count']} - X {point['x']:.1f}, Y {point['y']:.1f}, Z {point['z']:.1f}",
                "access_label": label,
                "access": access,
            })
        physical += len(entries)
        shrines[shrine_id] = entries

    quality_counts = {
        str(level): sum(entry["quality"] == level for entry in world.values())
        for level in (2, 3)
    }
    return {
        "schema_version": 1,
        "audit": {
            "world_chests": len(world),
            "dungeon_chests": len(dungeons),
            "shrine_entries": len(shrines),
            "physical_shrine_chests": physical,
            "world_access_types": dict(sorted(counts.items())),
            "world_quality_levels": quality_counts,
        },
        "sources": SOURCES,
        "world_chests": world,
        "dungeon_chests": dungeons,
        "shrines": shrines,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("botw_companion/data/catalog_fr_compiled.json"))
    parser.add_argument("--cartography", type=Path, default=Path("botw_companion/data/cartography_reference_fr_compiled.json"))
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("botw_companion/data/chest_reference.json"))
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    catalog = _payload_catalog(args.catalog)
    cartography = _read_json(args.cartography).get("reference", _read_json(args.cartography))
    if args.fetch:
        _fetch_all(args.cache, catalog["world_chests"], args.workers)
    payload = build(catalog, cartography, args.cache)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(payload["audit"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()