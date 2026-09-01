#!/usr/bin/env python3
"""Construit les stratégies hors ligne vérifiées des boss et mini-boss BOTW."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

SOURCES = {
    "object_map": {"name": "BOTW Object Map", "url": "https://objmap.zeldamods.org/"},
    "compendium": {"name": "Compendium d'Hyrule - ennemis BOTW", "url": "https://www.zeldadungeon.net/wiki/Breath_of_the_Wild_Hyrule_Compendium"},
    "hinox": {"name": "Zelda Dungeon - Hinox", "url": "https://www.zeldadungeon.net/wiki/Hinox"},
    "talus": {"name": "Zelda Dungeon - Lithorok", "url": "https://www.zeldadungeon.net/wiki/Stone_Talus"},
    "frost_talus": {"name": "Zelda Dungeon - Cryorok", "url": "https://www.zeldadungeon.net/wiki/Frost_Talus"},
    "igneo_talus": {"name": "Zelda Dungeon - Magrok", "url": "https://www.zeldadungeon.net/wiki/Igneo_Talus"},
    "molduga": {"name": "Zelda Dungeon - Moldarquor", "url": "https://www.zeldadungeon.net/wiki/Molduga"},
    "molduking": {"name": "Zelda Dungeon - Arquor Rex", "url": "https://www.zeldadungeon.net/wiki/Molduking"},
    "enemies": {"name": "Zelda Dungeon - ennemis de Breath of the Wild", "url": "https://www.zeldadungeon.net/wiki/Breath_of_the_Wild_Enemies"},
    "guardian_scout": {"name": "Zelda Dungeon - Nano Gardien 4.0", "url": "https://www.zeldadungeon.net/wiki/Guardian_Scout_IV"},
}


def _strategy(label: str, requirements: list[str], preparation: list[str], steps: list[str],
              weak_point: str, dangers: list[str], rewards: list[str], sources: list[str],
              *, scaling: str | None = None) -> dict:
    result = {
        "label": label, "quality": 3, "requirements": requirements,
        "preparation": preparation, "steps": steps, "weak_point": weak_point,
        "dangers": dangers, "rewards": rewards, "sources": [SOURCES[key] for key in sources],
    }
    if scaling:
        result["scaling"] = scaling
    return result


STRATEGIES = {
    "hinox": _strategy(
        "Hinox", ["Arc et flèches", "Arme de mêlée pour la fenêtre d'étourdissement"],
        ["Sauvegarder hors de sa zone de réveil", "Dégager les arbres qu'il pourrait arracher"],
        ["Approche pendant son sommeil et récupère discrètement les armes de son collier si tu le souhaites.",
         "À son réveil, vise l'œil : la touche le fait tomber et ouvre une longue fenêtre d'attaque.",
         "Frappe le corps ou les jambes pendant sa chute, puis éloigne-toi avant son écrasement au sol.",
         "Sous la moitié de sa vie il protège son œil : attends son attaque ou fige-le avec Cinetis+ avant de tirer."],
        "Œil unique", ["Écrasement de zone", "Arbres arrachés et lancés", "Protection de l'œil à faible vie"],
        ["Ongle, dent et viscères de Hinox", "Armes suspendues à son collier"], ["object_map", "hinox", "compendium"]),
    "blue_hinox": _strategy(
        "Hinox bleu", ["Arc et flèches", "Source de feu pour les jambières en bois"],
        ["Préparer une flèche de feu ou une arme enflammée", "Sauvegarder avant de le réveiller"],
        ["Brûle ses jambières en bois afin d'exposer ses jambes et de provoquer une réaction prolongée.",
         "Vise ensuite l'œil pour le faire tomber, puis concentre tes attaques pendant l'étourdissement.",
         "Recule avant son écrasement ou sa saisie, et évite les troncs qu'il arrache autour de lui.",
         "Quand il protège son œil sous la moitié de sa vie, tire pendant son attaque ou utilise Cinetis+."],
        "Œil ; jambières en bois vulnérables au feu", ["Écrasement", "Saisie", "Arbres lancés"],
        ["Ongle, dent et viscères de Hinox", "Armes de niveau intermédiaire portées au collier"], ["object_map", "hinox", "compendium"]),
    "black_hinox": _strategy(
        "Hinox noir", ["Arc et flèches", "Électricité recommandée contre les jambières métalliques"],
        ["Préparer une flèche électrique ou une arme de foudre", "Prévoir des soins contre ses dégâts élevés"],
        ["Électrise ses jambières métalliques pour provoquer une ouverture, ou attaque la jambe non protégée.",
         "Décoche une flèche dans l'œil dès qu'il est découvert, puis frappe fortement pendant sa chute.",
         "Éloigne-toi lorsqu'il se redresse : ses coups, sa saisie et son écrasement couvrent une large zone.",
         "Sous la moitié de sa vie, attends qu'il attaque et baisse sa main avant de viser de nouveau l'œil."],
        "Œil ; métal des jambières conducteur", ["Dégâts élevés", "Écrasement de zone", "Armes et arbres lancés"],
        ["Ongle, dent et viscères de Hinox", "Armes puissantes portées au collier"], ["object_map", "hinox", "compendium"]),
    "stalhinox": _strategy(
        "Stalhinox", ["Combattre de nuit", "Arc et flèches", "Arme de mêlée rapide pour l'œil séparé"],
        ["Arriver après la tombée de la nuit", "Commencer assez tôt pour terminer avant l'aube"],
        ["Attends la nuit complète : le squelette inerte pendant la journée ne peut pas être combattu normalement.",
         "Vise son œil pour l'étourdir, puis frappe son corps pendant qu'il est au sol.",
         "À faible vie, fais sortir l'œil avec une nouvelle flèche et attaque directement l'œil tombé.",
         "Détruis impérativement l'œil avant l'aube ; sinon le corps se reconstruit tant que l'œil reste intact."],
        "Œil détachable", ["Os et arbres lancés", "Reconstruction autour de l'œil", "Disparition à l'aube"],
        ["Dent de Hinox", "Armes portées au collier selon l'emplacement"], ["object_map", "hinox", "compendium"]),
    "stone_talus": _strategy(
        "Lithorok", ["Arme contondante ou lourde", "Bombes à distance"],
        ["Repérer si le gisement est au sommet, sur le côté ou dans le dos", "Garder de l'endurance pour l'escalade"],
        ["Réveille le Lithorok puis évite son premier coup ou son lancer de bras.",
         "Détruis un bras avec une bombe ou touche directement le gisement à l'arc pour le faire tomber.",
         "Grimpe sur son dos et frappe uniquement le gisement, seul point qui subit réellement les dégâts.",
         "Saute avant qu'il ne se secoue, puis répète l'ouverture après la reconstruction de ses bras."],
        "Gisement de minerai", ["Poings et bras projetés", "Écrasement", "Secousse qui éjecte Link"],
        ["Silex, ambre brut, opale brute et autres gemmes selon la variante"], ["object_map", "talus", "compendium"]),
    "luminous_talus": _strategy(
        "Lithorok nox", ["Arme contondante ou lourde", "Bombes"],
        ["Repérer la position du gisement lumineux", "Préserver une arme efficace contre les minerais"],
        ["Évite le lancer de bras et détruis un bras avec une bombe pour créer la première chute.",
         "Grimpe par l'arrière dès qu'il est abaissé et place-toi face au gisement lumineux.",
         "Frappe le gisement avec une arme contondante ou une attaque chargée à deux mains.",
         "Descends avant sa secousse, puis recommence après avoir détruit ses bras reconstruits."],
        "Gisement de pierre nox", ["Bras projetés", "Écrasement", "Éjection du sommet"],
        ["Pierres nox et assortiment de gemmes"], ["object_map", "talus", "compendium"]),
    "igneo_talus": _strategy(
        "Magrok", ["Protection ignifuge", "Flèche, arme ou baguette de glace", "Arme contondante"],
        ["Équiper la protection ignifuge de la région d'Ordinn", "Préparer plusieurs sources de froid"],
        ["Touche le Magrok avec une attaque de glace afin d'éteindre temporairement son corps brûlant.",
         "Profite de l'étourdissement pour grimper ; sans refroidissement, le contact inflige continuellement des dégâts.",
         "Frappe le gisement avec une arme contondante, puis saute dès que le corps commence à se rallumer.",
         "Évite l'explosion de son écrasement et refroidis-le de nouveau après qu'il a ravivé ses flammes."],
        "Gisement ; corps neutralisé par le froid", ["Contact brûlant", "Explosion des bras", "Rallumage du corps"],
        ["Silex, ambre, opale et rubis bruts"], ["object_map", "igneo_talus", "compendium"]),
    "frost_talus": _strategy(
        "Cryorok", ["Protection contre le froid", "Flèche, arme ou baguette de feu", "Arme contondante"],
        ["Équiper deux niveaux de protection contre le froid si nécessaire", "Préparer plusieurs sources de feu"],
        ["Fais fondre sa couche glacée avec une attaque de feu avant toute tentative d'escalade.",
         "Détruis un bras avec une bombe ou frappe le gisement à distance pour provoquer sa chute.",
         "Grimpe pendant la fenêtre dégelée et frappe le gisement avec une arme contondante.",
         "Saute lorsqu'il se secoue ou recommence à geler, puis applique de nouveau le feu avant de remonter."],
        "Gisement ; corps neutralisé par le feu", ["Gel au contact", "Bras projetés", "Regel du corps"],
        ["Silex, ambre, opale et saphir bruts"], ["object_map", "frost_talus", "compendium"]),
    "molduga": _strategy(
        "Moldarquor", ["Bombes à distance", "Arme puissante pour la phase au sol", "Protection contre la chaleur si nécessaire"],
        ["Repérer un rocher ou pilier hors du sable", "Éliminer les ennemis secondaires autour de l'arène"],
        ["Monte sur une surface rocheuse : le Moldarquor détecte les vibrations produites dans le sable.",
         "Lance une bombe sur le sable et attends qu'il fonce vers elle puis l'avale en bondissant.",
         "Déclenche la bombe pour l'étourdir, rejoins son ventre et attaque jusqu'aux premiers signes de réveil.",
         "Remonte immédiatement sur le rocher avant sa replongée et répète le cycle sans courir sur le sable."],
        "Ventre exposé après l'explosion avalée", ["Bond hors du sable", "Onde de choc", "Détection des pas"],
        ["Aileron et viscères de Moldarquor", "Coffre ou armes présents selon l'arène"], ["object_map", "molduga", "compendium"]),
    "molduking": _strategy(
        "Arquor Rex", ["DLC L'Ode aux Prodiges", "Bombes", "Armes puissantes", "Protection contre la chaleur"],
        ["Utiliser le grand pilier central comme zone sûre", "Prévoir une défense élevée contre ses attaques renforcées"],
        ["Reste sur une partie solide et attire l'Arquor Rex avec une bombe posée sur le sable.",
         "Fais exploser la bombe lorsqu'il l'avale durant son bond afin de le renverser.",
         "Frappe son ventre pendant l'étourdissement, mais surveille son réveil plus rapide qu'un Moldarquor ordinaire.",
         "Reviens sur le pilier avant sa replongée et évite les projectiles qu'il expulse à distance."],
        "Ventre après ingestion d'une bombe", ["Vitesse et puissance supérieures", "Projectiles", "Bond de grande portée"],
        ["Ailerons et viscères de Moldarquor", "Validation de l'épreuve de l'Ode aux Prodiges"], ["object_map", "molduking", "compendium"]),
    "lynel": _strategy(
        "Lynel", ["Bouclier", "Arc précis", "Arme puissante", "Repas de soin"],
        ["Identifier son arme avant l'engagement", "Rester à moyenne portée pour éviter qu'il utilise son arc"],
        ["Esquive latéralement ses charges et attaques verticales, ou recule sur les balayages, afin de déclencher une esquive parfaite.",
         "Décoche une flèche dans son visage lorsqu'il est de face : après l'étourdissement, cours derrière lui et monte-le.",
         "Frappe plusieurs fois depuis son dos ; ces coups montés préservent la durabilité de l'arme équipée.",
         "Éloigne-toi de son explosion de feu, utilise le courant ascendant pour viser en ralenti et recommence le cycle."],
        "Visage pour l'étourdissement", ["Charge", "Combo adapté à son arme", "Arc très précis à longue distance", "Explosion de feu"],
        ["Corne, sabot et viscères de Lynel", "Arc, bouclier et arme du Lynel"], ["object_map", "enemies", "compendium"]),
    "blue_lynel": _strategy(
        "Lynel bleu", ["Bouclier solide", "Arc précis", "Arme puissante", "Soins renforcés"],
        ["Identifier épée, lance ou espadon avant d'esquiver", "Préparer un bonus de défense ou d'attaque"],
        ["Observe son arme : esquive de côté les frappes verticales et en arrière les balayages afin de déclencher la ruée.",
         "Vise son visage après une attaque pour l'étourdir, passe derrière lui et monte-le.",
         "Attaque depuis son dos pour préserver la durabilité, puis prépare ton bouclier dès qu'il t'éjecte.",
         "Reste proche pour limiter son arc, évite l'explosion et exploite le courant de feu pour un nouveau tir ralenti."],
        "Visage", ["Dégâts supérieurs au Lynel rouge", "Arc à longue portée", "Explosion de feu"],
        ["Matériaux de Lynel", "Équipement de Lynel bleu"], ["object_map", "enemies", "compendium"]),
    "white_lynel": _strategy(
        "Lynel blanc", ["Plusieurs boucliers", "Arc précis", "Arme très puissante", "Soins complets"],
        ["Activer un bonus d'attaque ou de défense", "Identifier son arme et sauvegarder avant le combat"],
        ["Déclenche des esquives parfaites sur ses longues séries sans attaquer avant la fin de l'enchaînement.",
         "Place une flèche dans son visage pendant sa récupération, contourne-le et monte immédiatement sur son dos.",
         "Utilise ta meilleure arme pendant les coups montés qui n'en consomment pas la durabilité.",
         "Après l'éjection, garde tes distances avec l'explosion mais rapproche-toi avant qu'il ne sorte son arc."],
        "Visage", ["Très grande réserve de vie", "Longs combos", "Arc et explosion de feu"],
        ["Matériaux de Lynel de haut rang", "Équipement de Lynel blanc"], ["object_map", "enemies", "compendium"]),
    "scaling_lynel": _strategy(
        "Lynel évolutif", ["Équipement adapté au rang actuellement visible", "Bouclier", "Arc précis", "Soins"],
        ["Utiliser l'appareil photo ou la barre de vie pour confirmer son rang actuel", "Identifier son arme avant d'engager"],
        ["Confirme d'abord sa couleur : ce placement évolue de Lynel rouge à bleu, blanc puis argent selon la progression mondiale.",
         "Esquive selon son arme pour déclencher une ruée, puis vise son visage pendant la récupération.",
         "Après l'étourdissement, monte-le et utilise une arme puissante : les frappes montées préservent sa durabilité.",
         "Reste assez proche pour éviter son arc, écarte-toi de l'explosion de feu et répète le cycle."],
        "Visage", ["Rang variable", "Arme variable", "Arc à longue portée", "Explosion de feu"],
        ["Matériaux et équipement correspondant au rang actuel"], ["object_map", "enemies", "compendium"],
        scaling="La couleur dépend de la progression cachée du monde ; la fiche couvre explicitement les quatre rangs possibles."),
    "guardian_stalker": _strategy(
        "Gardien à pied", ["Boucliers pour la garde parfaite", "Arc", "Arme antique ou archéonique recommandée"],
        ["Sauvegarder avant sa zone d'activation", "Utiliser le décor pour couper la ligne de visée"],
        ["Approche par le côté et coupe ses six pattes une à une : chaque destruction l'interrompt et réduit sa mobilité.",
         "Vise son œil pour interrompre la charge du laser, puis frappe son corps pendant l'étourdissement.",
         "À distance, renvoie le laser avec une garde parfaite au moment du flash et du signal sonore.",
         "Une flèche antique dans l'œil peut l'éliminer immédiatement ; ramasse les pièces avant la prochaine lune de sang."],
        "Œil ; pattes destructibles", ["Laser", "Mobilité élevée", "Écrasement au contact"],
        ["Vis, ressorts, rouages, arbres et cœurs antiques"], ["object_map", "enemies", "compendium"]),
    "decayed_guardian": _strategy(
        "Gardien détérioré", ["Bouclier pour la garde parfaite", "Arc ou arme antique"],
        ["Observer si la carcasse s'active à l'approche", "Repérer un mur pour rompre le ciblage"],
        ["Approche en gardant un obstacle entre son œil et Link jusqu'à son activation.",
         "Tire dans l'œil pour interrompre le laser et profite de l'étourdissement pour attaquer.",
         "Comme il ne peut pas se déplacer, utilise la distance ou renvoie son laser avec une garde parfaite.",
         "Répète l'interruption ; une flèche antique dans l'œil constitue l'élimination la plus rapide."],
        "Œil", ["Laser", "Activation tardive de certaines carcasses"],
        ["Pièces antiques, avec probabilité dépendant de la carcasse"], ["object_map", "enemies", "compendium"]),
    "guardian_skywatcher": _strategy(
        "Gardien volant", ["Arc et réserve de flèches", "Bouclier", "Flèches explosives ou antiques recommandées"],
        ["Combattre depuis un couvert vertical", "Prévoir suffisamment de flèches pour les trois hélices"],
        ["Reste sous couvert et vise successivement ses trois hélices ; leur destruction finit par le mettre au sol.",
         "Interromps la charge du laser avec une flèche dans l'œil lorsque l'angle est dégagé.",
         "Une fois au sol, attaque son corps avec une arme antique ou renvoie son laser par garde parfaite.",
         "Pour une élimination directe, place une flèche antique exactement dans l'œil."],
        "Œil ; trois hélices destructibles", ["Laser aérien", "Déplacement qui complique la visée", "Chute de la carcasse"],
        ["Assortiment de pièces antiques"], ["object_map", "enemies", "compendium"]),
    "guardian_turret": _strategy(
        "Gardien tourelle", ["Boucliers", "Arc", "Arme antique recommandée"],
        ["Repérer un mur ou créneau du château", "Sauvegarder avant de quitter le couvert"],
        ["Utilise l'architecture du château pour rompre son ciblage et choisis une sortie courte vers sa ligne de vue.",
         "Vise l'œil pour interrompre le laser et profite de chaque étourdissement pour attaquer.",
         "À distance, renvoie le rayon avec une garde parfaite au moment du flash ; la tourelle ne peut pas te poursuivre.",
         "Une flèche antique dans l'œil permet une destruction immédiate si tu disposes d'un angle sûr."],
        "Œil", ["Portée supérieure", "Laser", "Angles croisés avec d'autres Gardiens du château"],
        ["Assortiment de pièces antiques"], ["object_map", "enemies", "compendium"]),
    "scout_2": _strategy(
        "Nano Gardien 2.0", ["Bouclier", "Arme de mêlée", "Piliers de l'arène"],
        ["Observer l'arme portée", "Conserver le pilier pour sa charge tournoyante"],
        ["Esquive latéralement l'attaque verticale ou en arrière le balayage afin de déclencher une ruée.",
         "Lorsqu'il recule pour tournoyer, place un pilier entre vous : la collision l'étourdit.",
         "À faible vie, utilise le courant ascendant de son laser rotatif pour tirer en ralenti.",
         "Interromps ou termine rapidement son laser chargé final, qui devient mortel s'il est laissé libre."],
        "Œil central", ["Arme de mêlée", "Rotation chargée", "Laser final"],
        ["Pièces antiques", "Arme de Gardien 1.0 ou 2.0 selon l'équipement"], ["object_map", "guardian_scout", "enemies"]),
    "scout_3": _strategy(
        "Nano Gardien 3.0", ["Bouclier solide", "Armes efficaces", "Piliers de l'arène"],
        ["Identifier ses deux armes", "Prévoir des soins pour l'épreuve moyenne"],
        ["Adapte l'esquive à chacune de ses deux armes et contre-attaque uniquement avec une ruée maîtrisée.",
         "Force sa charge tournoyante contre un pilier afin de l'étourdir sans user ton bouclier.",
         "Prends le courant ascendant créé par le laser rotatif et vise son œil en ralenti.",
         "Quand il plante ses armes et charge le laser final, attaque sans interruption ou renvoie le tir."],
        "Œil central", ["Combinaisons de deux armes", "Rotation", "Laser final"],
        ["Pièces antiques", "Armes de Gardien 2.0"], ["object_map", "guardian_scout", "enemies"]),
    "scout_4": _strategy(
        "Nano Gardien 4.0", ["Plusieurs armes solides", "Bouclier", "Arc", "Soins complets"],
        ["Identifier ses trois armes", "Préserver les piliers jusqu'à sa rotation"],
        ["Lis ses trois armes : salto arrière contre le balayage latéral, esquive de côté contre les coups verticaux ou d'estoc.",
         "Place un pilier entre vous lorsqu'il charge en rotation ; la collision ouvre une longue fenêtre d'attaque.",
         "Utilise le courant du laser rotatif pour prendre de la hauteur et tirer plusieurs flèches dans l'œil.",
         "À très faible vie, frappe sans relâche pendant son laser chargé ou renvoie le rayon avec une garde parfaite."],
        "Œil central", ["Trois armes antiques", "Rotation très dommageable", "Laser final"],
        ["Pièces antiques rares", "Armes de Gardien 3.0"], ["object_map", "guardian_scout", "enemies"]),
}

LAYER_TYPES = {
    "enemy_hinox", "enemy_talus", "enemy_molduga", "enemy_lynel",
    "enemy_guardian", "enemy_guardian_scout",
}


def strategy_key(item: dict) -> str:
    subtype = item.get("subtype", "")
    if subtype == "Hinox": return "hinox"
    if subtype == "Hinox bleu": return "blue_hinox"
    if subtype == "Hinox noir": return "black_hinox"
    if subtype == "Stalhinox": return "stalhinox"
    if subtype == "Lithorok": return "stone_talus"
    if subtype == "Lithorok nox": return "luminous_talus"
    if subtype == "Magrok": return "igneo_talus"
    if subtype == "Cryorok": return "frost_talus"
    if subtype == "Moldarquor": return "molduga"
    if subtype == "Arquor Rex": return "molduking"
    if subtype == "Lynel": return "lynel"
    if subtype == "Lynel bleu": return "blue_lynel"
    if subtype == "Lynel blanc": return "white_lynel"
    if "Lynel" in subtype and "/" in subtype: return "scaling_lynel"
    if subtype == "Gardien à pied": return "guardian_stalker"
    if subtype == "Gardien détérioré": return "decayed_guardian"
    if subtype == "Gardien volant": return "guardian_skywatcher"
    if subtype == "Gardien tourelle": return "guardian_turret"
    if "Nano Gardien 2.0" in subtype: return "scout_2"
    if "Nano Gardien 3.0" in subtype: return "scout_3"
    if "Nano Gardien 4.0" in subtype: return "scout_4"
    raise ValueError(f"Sous-type de boss non documenté : {subtype!r}")


def nearest(item: dict, layers: list[dict], layer_type: str) -> dict:
    candidates = [layer for layer in layers if layer.get("layer_type") == layer_type]
    result = min(candidates, key=lambda layer: math.hypot(item["x"] - layer["x"], item["z"] - layer["z"]))
    distance = math.hypot(item["x"] - result["x"], item["z"] - result["z"])
    if distance > 1:
        raise ValueError(f"Aucune variante à moins d'un mètre pour {item['id']} : {distance:.2f} m")
    return result


def build(catalog: dict) -> dict:
    layers = [item for item in catalog["map_layers"] if item.get("layer_type") in LAYER_TYPES]
    layer_entries = {
        item["id"]: {"strategy": strategy_key(item), "subtype": item["subtype"]}
        for item in layers
    }
    persistent = {}
    for group, layer_type in (("hinoxes", "enemy_hinox"), ("taluses", "enemy_talus"),
                              ("moldugas", "enemy_molduga")):
        for item in catalog[group]:
            match = nearest(item, layers, layer_type)
            persistent[item["id"]] = {
                "strategy": strategy_key(match), "subtype": match["subtype"],
                "layer_id": match["id"],
            }
    return {
        "schema_version": 1,
        "strategies": STRATEGIES,
        "persistent": persistent,
        "map_layers": layer_entries,
        "audit": {
            "strategies": len(STRATEGIES),
            "persistent_bosses": len(persistent),
            "map_combat_points": len(layer_entries),
            "scripted_bosses_already_complete": len(catalog["scripted_bosses"]),
            "persistent_by_strategy": dict(sorted(Counter(x["strategy"] for x in persistent.values()).items())),
            "map_by_strategy": dict(sorted(Counter(x["strategy"] for x in layer_entries.values()).items())),
        },
        "sources": list(SOURCES.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("botw_companion/data/catalog_fr_compiled.json"))
    parser.add_argument("--output", type=Path, default=Path("botw_companion/data/boss_reference.json"))
    args = parser.parse_args()
    payload = json.loads(args.catalog.read_text(encoding="utf-8"))
    catalog = payload.get("catalog", payload)
    result = build(catalog)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(result["audit"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()