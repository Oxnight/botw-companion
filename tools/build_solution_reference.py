#!/usr/bin/env python3
"""Construit le référentiel factuel des fiches (quêtes et Épreuves de l'Épée)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


SOURCE_TRIALS = {
    "name": "Zelda Dungeon - Trial of the Sword",
    "url": "https://www.zeldadungeon.net/wiki/Trial_of_the_Sword",
}


TRIAL_FLOORS = {
    "beginning": [
        ("combat", "3 Bokoblins", "Utilise l'arbre comme couvert, puis une bombe près du feu ; récupère immédiatement armes et nourriture."),
        ("combat", "1 Chuchu de feu, 4 Bokoblins", "Élimine le Chuchu depuis le grand arbre, puis déloge séparément les archers avec des bombes."),
        ("combat", "1 Chuchu, 8 Chuchus de feu", "Fais exploser les Chuchus à distance et exploite les courants ascendants avant que l'herbe ne cesse de brûler."),
        ("combat", "5 Bokoblins, 3 Bokoblins bleus", "Approche discrètement, neutralise d'abord les archers et déclenche les barils depuis une position sûre."),
        ("combat", "2 Moblins, 3 Bokoblins bleus", "Tire une flèche de feu dans la grotte-crâne, puis bombarde les survivants depuis les arbres."),
        ("combat", "1 Lithorok", "Détruis ses bras avec les bombes, grimpe pendant sa chute et frappe le gisement avec une arme à deux mains."),
        ("rest", "Aucun", "Approche accroupi pour capturer la fée, brise les caisses et cuisine les ingrédients avant de repartir."),
        ("combat", "1 gros Chuchu électrique, 2 Lézalfos, 2 Lézalfos bleus", "Élimine le Chuchu depuis le rocher, saisis la lance et isole les Lézalfos avec Cinetis."),
        ("combat", "2 Octos d'eau, 1 Sorcier électrique", "Tue l'Octo placé derrière le départ, sors le coffre avec Cryonis puis maintiens le Sorcier au sol."),
        ("combat", "1 Lézalfos bleu, 2 Lézalfos noirs", "Crée un pilier Cryonis pour tirer en ralenti, puis concentre toutes les attaques sur une cible à la fois."),
        ("combat", "4 Bokoblins, 3 Bokoblins bleus, 1 Bokoblin noir, 1 Moblin noir", "Élimine les archers avant d'avancer avec le radeau et fais tomber le Moblin dans l'eau si possible."),
        ("combat", "1 Hinox bleu", "Vise l'œil, exploite Cinetis amélioré et frappe avec une arme à deux mains pendant chaque chute."),
        ("reward", "Aucun", "Examine le moine pour renforcer l'Épée de légende : puissance de base 40."),
    ],
    "middle": [
        ("combat", "5 Bokoblins", "Laisse les bombes flotter sous les plateformes pour économiser les armes, puis ouvre le coffre à droite."),
        ("combat", "2 Bokoblins, 1 Bokoblin bleu, 1 Sorcier de feu, 2 Sorciers météores", "Élimine les Sorciers à l'arc avant qu'ils ne modifient la météo, puis termine les Bokoblins."),
        ("combat", "4 Bokoblins, 3 Bokoblins bleus", "Utilise les courants d'air pour les tirs en ralenti et fais tomber les ennemis des plateformes."),
        ("combat", "1 Gardien détérioré", "Place un obstacle entre le laser et Link, vise l'œil puis frappe pendant l'interruption."),
        ("rest", "Aucun", "Capture la fée, ouvre les trois coffres et cuisine avant la section plongée dans l'obscurité."),
        ("combat", "5 Chauves-souris de feu, 1 Chuchu électrique", "Dans l'obscurité, repère les lueurs, élimine les Chauves-souris à distance puis le Chuchu."),
        ("combat", "2 Lézalfos crache-feu, 2 Lézalfos bleus", "Utilise la glace contre les crache-feu et combats une cible à la fois dans la zone éclairée."),
        ("combat", "1 Sorcier météore, 2 Bokoblins bleus, 1 Bokoblin noir", "Abats d'abord le Sorcier pour éviter ses renforts, puis utilise son arme de feu comme source de lumière."),
        ("combat", "1 Gardien détérioré", "Repère son œil dans l'obscurité, protège-toi derrière le décor et renvoie ou interrompt le laser."),
        ("combat", "1 Hinox noir", "Prépare une attaque renforcée, vise l'œil et utilise les meilleures armes durant son étourdissement."),
        ("rest", "Aucun", "Capture les deux fées, ouvre les trois coffres et cuisine toute la nourriture utile."),
        ("combat", "6 Nano Gardiens I", "Isole les éclaireurs et utilise Cryonis pour atteindre le coffre de dix flèches."),
        ("combat", "3 Nano Gardiens II", "Déplace la caisse métallique pour atteindre le coffre caché, puis élimine les Gardiens sans gaspiller les armes fortes."),
        ("combat", "4 Nano Gardiens I, 2 Nano Gardiens II", "Concentre les attaques sur les modèles II et utilise les piliers pour casser les lignes de tir."),
        ("combat", "2 Nano Gardiens III", "Provoque les esquives parfaites et abrite-toi lorsque commence l'attaque tournoyante."),
        ("combat", "1 Nano Gardien IV", "Économise une arme solide, exploite chaque esquive parfaite et les courants ascendants du laser rotatif."),
        ("reward", "Aucun", "Examine le moine pour renforcer l'Épée de légende : puissance de base 50."),
    ],
    "final": [
        ("combat", "4 Stalkoblins", "Utilise surtout les bombes, détruis les crânes et conserve toutes les armes en bois pour la suite."),
        ("combat", "2 Chauves-souris électriques, 3 Stalézalfos", "Élimine les Chauves-souris, déclenche les barils avec une bombe et détruis rapidement les crânes."),
        ("combat", "2 Chuchus électriques, 5 Stalmoblins", "Fais exploser les Chuchus à distance puis utilise les bombes pour désarmer et finir les Stalmoblins."),
        ("combat", "7 Stalkoblins montés", "Vole un cheval squelette, saute pour tirer en ralenti et vise la tête des cavaliers."),
        ("combat", "1 Stalhinox", "Décroche son œil, détruis-le avant l'aube et récupère les trois armes élémentaires fixées à son corps."),
        ("rest", "Aucun", "Capture les deux fées et conserve précieusement les trois flèches archéoniques pour les dernières salles."),
        ("combat", "1 Chuchu de feu, 1 Octo des rochers, 2 Lithoroks juniors de feu", "Reste à distance : les bombes suffisent pour nettoyer toute cette salle volcanique."),
        ("combat", "3 Lézalfos crache-feu", "Utilise les courants ascendants pour viser la tête puis élimine-les avec l'arme de glace."),
        ("combat", "1 Sorcier météore, 1 Moblin noir, 2 Lézalfos crache-feu", "Neutralise le Sorcier en premier et conserve son bâton météore pour la section froide."),
        ("combat", "3 Moblins noirs, 1 Lézalfos crache-feu", "Utilise Cinetis et l'électricité ; empêche les Moblins de tomber dans la lave afin de récupérer leurs armes."),
        ("combat", "1 Magrok", "Refroidis son corps avec la glace, exploite les courants ascendants et frappe le gisement."),
        ("rest", "Aucun", "Capture les trois fées, ouvre les coffres et cuisine plusieurs plats anti-froid pour la prochaine section."),
        ("combat", "2 Lithoroks juniors de glace, 1 Chuchu de glace, 2 Bokoblins bleus, 1 Bokoblin noir", "Utilise le feu contre les ennemis gelés et profite de la dernière marmite disponible."),
        ("combat", "2 Chuchus de glace, 1 Lézalfos crache-glace, 4 Bokoblins bleus, 1 Moblin argenté", "Élimine les cibles de glace avec le feu et récupère les trois flèches archéoniques du coffre."),
        ("combat", "1 Moblin noir, 1 Sorcier de glace, 2 Bokoblins bleus, 1 Bokoblin argenté", "Abats le Sorcier avec le feu avant qu'il n'invoque des renforts, puis isole les ennemis lourds."),
        ("combat", "1 Cryorok", "Fais fondre sa glace, utilise le brise-pierre de la salle de repos et frappe le gisement."),
        ("combat", "1 Lynel bleu", "La neige gêne les déplacements : utilise une flèche archéonique pour préserver santé et équipement."),
        ("rest", "Aucun", "Capture les quatre fées, cuisine un repas de soin complet et ouvre les trois coffres royaux."),
        ("combat", "6 Gardiens détériorés", "Utilise les arbres pour couper les tirs, attaque chaque Gardien par l'arrière et conserve les flèches archéoniques."),
        ("combat", "1 Gardien à pied", "Coupe ses pattes, vise l'œil et combats-le normalement afin d'économiser les flèches archéoniques."),
        ("combat", "1 Gardien volant", "Prends de la hauteur avec les tours, détruis ses hélices ou utilise une flèche archéonique."),
        ("combat", "1 Gardien à pied, 1 Gardien volant, 1 Gardien tourelle", "Élimine le volant et le marcheur aux flèches archéoniques, puis grimpe jusqu'à la tourelle si nécessaire."),
        ("combat", "8 Bokoblins montés, 1 Lynel blanc, 1 Gardien tourelle", "Supprime immédiatement le Lynel avec une flèche archéonique, neutralise la tourelle puis termine les cavaliers."),
        ("reward", "Aucun", "Examine le moine : l'Épée de légende conserve désormais sa puissance de base 60."),
    ],
}


def quest_evidence(catalog: dict, event_dir: Path) -> dict:
    result = {}
    for category in ("main_quests", "shrine_quests", "side_quests"):
        for item in catalog.get(category, []):
            internal_id = item["quest_internal_id"]
            path = event_dir / f"{internal_id}.json"
            nodes = json.loads(path.read_text()) if path.exists() else []
            actions = [node.get("data", {}).get("action") for node in nodes if node.get("node_type") == "action"]
            messages = sorted({
                str(value) for node in nodes for key, value in (node.get("data", {}).get("params") or {}).items()
                if "MessageId" in key
            })
            result[internal_id] = {
                "event_flow_found": path.exists(),
                "event_nodes": sum(node.get("type") == "node" for node in nodes),
                "event_actions": len([value for value in actions if value]),
                "message_references": len(messages),
                "source": {
                    "name": "BOTW Event Flow Viewer - flux de quête",
                    "url": "https://eventviewer.zeldamods.org/viewer.html?data=%2Fd%2F" + internal_id + ".json",
                },
            }
    return result


def trial_rooms() -> list[dict]:
    labels = {"beginning": "Épreuves basiques", "middle": "Épreuves moyennes", "final": "Épreuves extrêmes"}
    rooms = []
    for stage, floors in TRIAL_FLOORS.items():
        for number, (kind, enemies, strategy) in enumerate(floors, 1):
            rooms.append({
                "id": f"{stage}-{number:02d}", "stage": stage, "stage_label": labels[stage],
                "floor": number, "kind": kind,
                "kind_label": {"combat": "Salle active", "rest": "Salle de repos", "reward": "Salle de récompense"}[kind],
                "enemies": enemies, "strategy": strategy, "source": SOURCE_TRIALS,
            })
    return rooms


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--event-viewer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text())
    rooms = trial_rooms()
    quests = quest_evidence(catalog, args.event_viewer / "d")
    data = {
        "schema_version": 1,
        "quests": quests,
        "trial_rooms": rooms,
        "audit": {
            "quests_total": 152,
            "quests_with_event_flow_file": sum(item["event_flow_found"] for item in quests.values()),
            "quests_with_nonempty_event_flow": sum(item["event_nodes"] > 0 for item in quests.values()),
            "trial_rooms_total": len(rooms),
            "trial_active_rooms": sum(room["kind"] == "combat" for room in rooms),
            "trial_rest_rooms": sum(room["kind"] == "rest" for room in rooms),
            "trial_reward_rooms": sum(room["kind"] == "reward" for room in rooms),
        },
        "sources": [SOURCE_TRIALS, {
            "name": "BOTW Event Flow Viewer - données de flux",
            "url": "https://github.com/zeldamods/botw-event-viewer",
        }],
    }
    assert data["audit"] == {
        "quests_total": 152, "quests_with_event_flow_file": 152,
        "quests_with_nonempty_event_flow": 149, "trial_rooms_total": 54,
        "trial_active_rooms": 45, "trial_rest_rooms": 6, "trial_reward_rooms": 3,
    }
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()