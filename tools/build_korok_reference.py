#!/usr/bin/env python3
"""Construit la référence hors ligne des 900 énigmes Korogus vérifiées."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


TYPES = {
    "Rock Lift": ("Pierre à soulever", ["Rejoins précisément le point indiqué et repère la petite pierre isolée.", "Soulève cette pierre avec l'action Prendre.", "Examine le Korogu apparu et récupère la noix."]),
    "Rock Pattern": ("Motif de pierres", ["Repère le motif de pierres incomplet autour du point indiqué.", "Trouve la pierre mobile voisine et pose-la dans l'espace qui complète le motif.", "Examine le Korogu apparu et récupère la noix."]),
    "Cube Puzzle": ("Puzzle de cubes", ["Compare les deux assemblages de cubes métalliques au point indiqué.", "Utilise Polaris pour déplacer le cube libre et reproduire exactement l'autre assemblage.", "Valide le motif symétrique puis récupère la noix auprès du Korogu."]),
    "Goal Ring (Race)": ("Course vers l'anneau", ["Active la souche marquée par une feuille au point de départ.", "Rejoins l'anneau lumineux avant la fin du compte à rebours en suivant le parcours indiqué.", "Traverse entièrement l'anneau puis récupère la noix auprès du Korogu."]),
    "Stationary Lights": ("Lueur fixe", ["Rejoins le point exact et repère la petite lueur ou le tourbillon de feuilles immobile.", "Place-toi au contact de la lueur puis utilise Examiner.", "Laisse le Korogu apparaître et récupère la noix."]),
    "Flower Trail": ("Parcours de fleurs", ["Commence à la première fleur jaune au point de départ.", "Touche chaque nouvelle fleur qui apparaît et suis leur parcours dans l'ordre.", "Atteins la dernière fleur blanche puis récupère la noix auprès du Korogu."]),
    "Pinwheel Balloons": ("Moulinet et ballons", ["Place-toi près du moulinet au point indiqué pour faire apparaître les cibles.", "Observe tout autour de toi et détruis chaque ballon avec des flèches.", "Après la disparition de la dernière cible, récupère la noix auprès du Korogu."]),
    "Rock Lift (Rock Pile)": ("Pierre sous un amas", ["Repère l'amas de rochers fissurés qui recouvre le point indiqué.", "Détruis l'amas avec une bombe ou une arme adaptée, puis soulève la petite pierre révélée.", "Examine le Korogu apparu et récupère la noix."]),
    "Moving Lights": ("Lueur mobile", ["Repère la lueur mobile ou le tourbillon de feuilles autour du point indiqué.", "Anticipe sa trajectoire, approche-toi et utilise Examiner lorsqu'il passe à portée.", "Laisse le Korogu apparaître et récupère la noix."]),
    "Dive": ("Plongeon dans un cercle", ["Place-toi au-dessus du cercle de nénuphars ou de pierres situé au point indiqué.", "Saute d'assez haut et entre dans l'eau en plongeant au centre sans toucher le bord.", "Après le plongeon validé, récupère la noix auprès du Korogu."]),
    "Roll a Boulder": ("Rocher à faire rouler", ["Repère le gros rocher et le trou creux associés au point indiqué.", "Pousse le rocher ou utilise Cinetis et des impacts pour le faire entrer dans le trou.", "Lorsque le rocher reste dans la cavité, récupère la noix auprès du Korogu."]),
    "Acorn in a Hole": ("Gland dans une ouverture", ["Inspecte les troncs, arbres ou ouvertures autour du point indiqué pour trouver le gland caché.", "Vise le gland à travers l'ouverture et détruis-le avec une flèche.", "Après le tir réussi, récupère la noix auprès du Korogu."]),
    "Offering Plate": ("Offrande à compléter", ["Compare les coupelles ou statues d'offrande au point indiqué et repère celle qui est vide.", "Ramasse le même fruit ou aliment que dans les autres coupelles et dépose-le dans l'emplacement vide.", "Quand les offrandes correspondent, récupère la noix auprès du Korogu."]),
    "Stationary Balloon": ("Ballon caché", ["Cherche le ballon immobile dissimulé dans le décor autour du point indiqué.", "Trouve un angle de tir dégagé et détruis le ballon avec une flèche.", "Après le tir réussi, récupère la noix auprès du Korogu."]),
    "Matching Trees": ("Arbres fruitiers identiques", ["Compare les fruits portés par les arbres alignés autour du point indiqué.", "Retire uniquement les fruits en trop afin que les trois arbres présentent exactement le même motif.", "Lorsque les arbres correspondent, récupère la noix auprès du Korogu."]),
    "Circle of Rocks": ("Cercle de pierres dans l'eau", ["Repère le cercle de pierres dans l'eau depuis le point indiqué.", "Prends une pierre proche et lance-la pour qu'elle retombe à l'intérieur du cercle.", "Après un lancer validé, récupère la noix auprès du Korogu."]),
    "Rock Lift (Leaves)": ("Pierre sous des feuilles", ["Repère les feuilles sèches qui recouvrent le point indiqué.", "Brûle-les ou coupe-les, puis soulève la petite pierre qu'elles cachaient.", "Examine le Korogu apparu et récupère la noix."]),
    "Melt Ice Block": ("Bloc de glace à faire fondre", ["Rejoins le bloc de glace au point indiqué.", "Approche une source de chaleur ou utilise une arme de feu jusqu'à faire fondre complètement la glace.", "Examine la lueur révélée puis récupère la noix auprès du Korogu."]),
    "Ball and Chain": ("Boule reliée par une chaîne", ["Repère la boule métallique et son réceptacle au point indiqué.", "Utilise Polaris pour soulever la boule et la déposer dans le trou, le tronc ou le puits associé.", "Quand la boule reste dans son réceptacle, récupère la noix auprès du Korogu."]),
    "Hanging Acorn": ("Gland suspendu", ["Cherche le gland suspendu sous une branche, un pont ou une structure au point indiqué.", "Vise soigneusement et détruis le gland avec une flèche.", "Après le tir réussi, récupère la noix auprès du Korogu."]),
    "Rock Lift (Slab)": ("Pierre sous une dalle", ["Repère la grande dalle qui recouvre le point indiqué.", "Déplace la dalle avec Cinetis ou un autre moyen physique, puis soulève la petite pierre dessous.", "Examine le Korogu apparu et récupère la noix."]),
    "Flower Order": ("Fleurs numérotées", ["Repère les groupes de fleurs autour du point indiqué.", "Touche-les dans l'ordre croissant : une fleur, puis deux, trois, quatre et cinq.", "Après le cinquième groupe, récupère la noix auprès du Korogu."]),
    "Pinwheel Acorns": ("Moulinet et glands mobiles", ["Place-toi près du moulinet au point indiqué pour déclencher les cibles.", "Suis les glands mobiles et détruis-les tous avec des flèches ; Cinetis peut faciliter la visée.", "Après la dernière cible, récupère la noix auprès du Korogu."]),
    "Rock Lift (Door)": ("Pierre sous une plaque métallique", ["Repère la plaque ou porte métallique qui recouvre le point indiqué.", "Soulève-la avec Polaris, puis prends la petite pierre révélée dessous.", "Examine le Korogu apparu et récupère la noix."]),
    "Rock Lift (Boulder)": ("Pierre sous un gros rocher", ["Repère le gros rocher posé au-dessus du point indiqué.", "Déplace-le avec Cinetis, des impacts ou la pente, puis soulève la petite pierre dessous.", "Examine le Korogu apparu et récupère la noix."]),
    "Shoot the Crest": ("Emblème à viser", ["Repère l'emblème ou le blason visible depuis le point indiqué.", "Vise son centre et tire une flèche pour déclencher l'énigme.", "Après le tir validé, récupère la noix auprès du Korogu."]),
    "Jump the Fences": ("Parcours de clôtures", ["Monte à cheval et place-toi au départ du parcours près du point indiqué.", "Saute successivement toutes les clôtures sans contourner ni interrompre le parcours.", "Après le dernier saut validé, récupère la noix auprès du Korogu."]),
    "Light Torch": ("Torche à allumer", ["Repère la torche éteinte au point indiqué.", "Allume-la avec une flèche de feu, une arme enflammée ou une flamme transportée.", "Lorsque la torche brûle, récupère la noix auprès du Korogu."]),
    "Take the Stick": ("Branche à retirer", ["Rejoins le point indiqué et repère la branche placée dans le décor.", "Prends la branche pour rompre l'arrangement inhabituel.", "Après son retrait, récupère la noix auprès du Korogu."]),
    "Remove Luminous Stone": ("Pierre lumineuse à retirer", ["Repère le gisement ou la pierre lumineuse qui couvre le point indiqué.", "Brise ou retire la pierre lumineuse pour révéler l'élément caché.", "Examine le Korogu apparu et récupère la noix."]),
    "Burn the Leaves (Goatee)": ("Feuilles à brûler", ["Repère la forme de feuilles sèches au point indiqué.", "Enflamme entièrement les feuilles avec du feu.", "Examine la lueur révélée puis récupère la noix auprès du Korogu."]),
    "Shoot the Targets": ("Cibles à détruire", ["Place-toi au point indiqué et repère les cibles qui apparaissent autour de toi.", "Détruis toutes les cibles avec des flèches avant qu'elles ne disparaissent.", "Après la dernière cible, récupère la noix auprès du Korogu."]),
    "Take Apple from Palm Tree": ("Pomme intruse dans un palmier", ["Rejoins le palmier indiqué et repère la pomme inhabituelle parmi ses fruits.", "Grimpe ou utilise une flèche pour détacher précisément la pomme.", "Ramasse-la puis récupère la noix auprès du Korogu."]),
}

REQUIREMENTS = {
    "Cube Puzzle": ["Module Polaris"], "Ball and Chain": ["Module Polaris"],
    "Rock Lift (Door)": ["Module Polaris"], "Goal Ring (Race)": ["Endurance ou moyen de déplacement adapté au parcours"],
    "Pinwheel Balloons": ["Arc et flèches"], "Pinwheel Acorns": ["Arc et flèches"],
    "Stationary Balloon": ["Arc et flèches"], "Hanging Acorn": ["Arc et flèches"],
    "Acorn in a Hole": ["Arc et flèches"], "Shoot the Crest": ["Arc et flèches"],
    "Shoot the Targets": ["Arc et flèches"], "Rock Lift (Slab)": ["Module Cinetis ou moyen de déplacer la dalle"],
    "Rock Lift (Boulder)": ["Module Cinetis ou moyen de déplacer le rocher"],
    "Roll a Boulder": ["Module Cinetis recommandé"], "Jump the Fences": ["Cheval enregistré et suffisamment docile"],
    "Light Torch": ["Source de feu"], "Melt Ice Block": ["Source de chaleur"],
    "Rock Lift (Leaves)": ["Arme tranchante ou source de feu"], "Burn the Leaves (Goatee)": ["Source de feu"],
}


def parse_data_cpp(path: Path) -> tuple[dict[int, dict], dict[str, list[dict]]]:
    text = path.read_text(encoding="utf-8")
    koroks = {}
    pattern = re.compile(r'Data::Korok\((\d+), "([^"]+)", (-?[\d.]+)f?, (-?[\d.]+)f?, (\d+)\)')
    for save_hash, flag, x, z, guide_id in pattern.findall(text):
        object_hash = int(flag.rsplit("_", 1)[-1])
        koroks[object_hash] = {"save_hash": int(save_hash), "flag": flag, "x": float(x), "z": float(z), "guide_id": int(guide_id)}
    paths = {}
    path_pattern = re.compile(r'\{"(MainField_Npc_HiddenKorok[^\"]+)", \{([^\n]+)\}\}')
    point_pattern = re.compile(r'glm::vec2\((-?[\d.]+)f?, (-?[\d.]+)f?\)')
    for flag, raw in path_pattern.findall(text[text.index("void LoadPaths()"):]):
        points = [{"x": float(x), "z": float(z)} for x, z in point_pattern.findall(raw)]
        if points:
            paths[flag] = points
    return koroks, paths


def load_radar(directory: Path) -> dict[int, dict]:
    result = {}
    for path in sorted(directory.glob("*.json")):
        for row in json.loads(path.read_text(encoding="utf-8")):
            result[int(row["hash_id"])] = row
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-cpp", type=Path, required=True)
    parser.add_argument("--radar-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, paths = parse_data_cpp(args.data_cpp)
    radar = load_radar(args.radar_dir)
    if len(source) != 900 or len(radar) != 900 or set(source) != set(radar):
        raise SystemExit(f"Couverture invalide : source={len(source)}, radar={len(radar)}, communs={len(set(source) & set(radar))}")
    entries = {}
    type_counts = Counter()
    for object_hash in sorted(source):
        base, row = source[object_hash], radar[object_hash]
        puzzle_type = row["korok_type"]
        if puzzle_type not in TYPES:
            raise SystemExit(f"Type non documenté : {puzzle_type}")
        label, steps = TYPES[puzzle_type]
        points = paths.get(base["flag"], [])
        geo_points = []
        for index, point in enumerate(points):
            role = "Départ" if index == 0 else ("Arrivée" if index == len(points) - 1 else f"Point {index + 1}")
            geo_points.append({**point, "label": role})
        entry = {
            "save_hash": base["save_hash"],
            "object_hash": object_hash,
            "flag": base["flag"],
            "map_id": row["korok_id"],
            "map_unit": row["map_name"],
            "guide_id": base["guide_id"],
            "puzzle_type": puzzle_type,
            "puzzle_label": label,
            "x": round(float(row["pos"][0]), 2),
            "y": round(float(row["pos"][1]), 2),
            "z": round(float(row["pos"][2]), 2),
            "requirements": REQUIREMENTS.get(puzzle_type, ["Aucun module particulier requis"]),
            "steps": steps,
        }
        if geo_points:
            entry["geo_points"] = geo_points
        entries[base["flag"]] = entry
        type_counts[puzzle_type] += 1
    payload = {
        "schema_version": 1,
        "audit": {
            "total": len(entries), "types": len(type_counts), "with_paths": len(paths),
            "type_counts": dict(sorted(type_counts.items())),
        },
        "sources": [
            {"name": "BOTW Object Map", "url": "https://objmap.zeldamods.org/"},
            {"name": "Zelda Dungeon - 900 Korok Seed Locations", "url": "https://www.zeldadungeon.net/breath-of-the-wild-walkthrough/korok-seed-locations/"},
            {"name": "BotW Unexplored - correspondances et parcours Korogus", "url": "https://github.com/lud99/botw-unexplored"},
        ],
        "entries": entries,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(entries)} Korogus, {len(type_counts)} types, {len(paths)} parcours -> {args.output}")


if __name__ == "__main__":
    main()