from __future__ import annotations

import re


# Corrections de présentation vérifiées contre les textes français européens du jeu.
# Les identifiants, acteurs et flags ne passent jamais par cette table.
DISPLAY_EXACT = {
    "Filet archéonique": "Filet antique",
    "Selle archéonique": "Selle antique",
    "Bouclier Hylien": "Bouclier d'Hylia",
    "Armure Dieu démon": "Armure du Dieu démon",
    "Savoir quans s'arrêter": "Savoir quand s'arrêter",
    "Préparation pyschologique": "Préparation psychologique",
    "DLC 1 - Les Épreuves légendaires": "DLC 1 - Les épreuves légendaires",
    "DLC 2 - Ode aux Prodiges": "DLC 2 - L'Ode aux Prodiges",
    "Mode Expert": "Mode expert",
    "Malanya": "Marlon",
    "Réveiller Malanya": "Réveiller Marlon",
    "Malanya libéré": "Marlon libéré",
    "Fontaine de Malanya": "Fontaine de Marlon",
    "Épreuves de l'Épée": "Épreuves de l'épée",
    "Épreuve finale": "Épreuve finale de l'épée",
    "main_quests": "Quête principale",
    "shrine_quests": "Quête de sanctuaire",
    "side_quests": "Quête secondaire",
    "Sunken Trésors": "Trésors engloutis",
    "Small Key": "Petite clé",
}

REGIONS = {
    "Central": "Centre d'Hyrule",
    "Hyrule central": "Centre d'Hyrule",
    "Woodland": "Grande Forêt d'Hyrule",
    "Forêt d'Hyrule": "Grande Forêt d'Hyrule",
    "Wasteland": "Landes sauvages",
    "Trial of the Sword": "Épreuves de l'épée",
    "Épreuves de l'Épée": "Épreuves de l'épée",
    "Épreuve finale": "Épreuve finale de l'épée",
}


def _one_enemy(actor: str, previous: str) -> str:
    if "Bokoblin" in actor:
        if "Bone" in actor:
            return "Stalbokoblin"
        if "Dark" in actor:
            return "Bokoblin d'argent"
        if "Senior" in actor:
            return "Bokoblin noir"
        if "Middle" in actor:
            return "Bokoblin bleu"
        return "Bokoblin"
    if "Moriblin" in actor:
        if "Bone" in actor:
            return "Stalmoblin"
        if "Dark" in actor:
            return "Moblin d'argent"
        if "Senior" in actor:
            return "Moblin noir"
        if "Middle" in actor:
            return "Moblin bleu"
        return "Moblin"
    if "Lizalfos" in actor:
        if "Bone" in actor:
            return "Stalézalfos"
        if "Dark" in actor:
            return "Lézalfos d'argent"
        if "Electric" in actor:
            return "Lézalfos électrique"
        if "Fire" in actor:
            return "Lézalfos de feu"
        if "Ice" in actor:
            return "Lézalfos de glace"
        if "Senior" in actor:
            return "Lézalfos noir"
        if "Middle" in actor:
            return "Lézalfos bleu"
        return "Lézalfos"
    if "Lynel" in actor:
        if "Dark" in actor:
            return "Lynel d'argent"
        if "Senior" in actor:
            return "Lynel blanc"
        if "Middle" in actor:
            return "Lynel bleu"
        return "Lynel"
    if "Chuchu" in actor:
        name = ("Chuchu électrique" if "Electric" in actor else
                "Chuchu de feu" if "Fire" in actor else
                "Chuchu de glace" if "Ice" in actor else "Chuchu")
        size = ("petite taille" if "Junior" in actor else
                "taille moyenne" if "Middle" in actor else "grande taille")
        return f"{name} - {size}"
    if "Giant" in actor:
        if "Bone" in actor:
            return "Stalhinox"
        if "Senior" in actor:
            return "Hinox noir"
        if "Middle" in actor:
            return "Hinox bleu"
        return "Hinox"
    if "Wizzrobe" in actor:
        if "Electric_Senior" in actor:
            return "Sorcier fulguro"
        if "Fire_Senior" in actor:
            return "Sorcier brasero"
        if "Ice_Senior" in actor:
            return "Sorcier blizzaro"
        if "Electric" in actor:
            return "Sorcier électrique"
        if "Fire" in actor:
            return "Sorcier de feu"
        return "Sorcier de glace"
    if "Assassin" in actor:
        return "Officier Yiga" if "Middle" in actor and "Shooter" not in actor else "Sous-fifre Yiga"
    if "Octarock" in actor:
        if "Air" in actor:
            return "Octociel - mode expert"
        if "Forest" in actor:
            return "Octofourré"
        if "Stone" in actor:
            return "Octopierre"
        if "Desert" in actor:
            return "Octocoffre"
        if "Snow" in actor:
            return "Octoneige"
        return "Octoflot"
    if "Golem_Little_Fire" in actor:
        return "Migrok"
    if "Golem_Little_Ice" in actor:
        return "Givrok"
    if "Golem_Little" in actor:
        return "Tilhorok"
    if "Golem_Fire" in actor:
        return "Magrok"
    if "Golem_Ice" in actor or "Golem_Middle" in actor:
        return "Cryorok"
    if "Golem_Senior" in actor:
        return "Lithorok nox"
    if "Golem_Junior" in actor:
        return "Lithorok"
    if "SandwormR" in actor:
        return "Arquor Rex"
    if "Sandworm" in actor:
        return "Moldarquor"
    if "Guardian_A_Fixed" in actor:
        return "Gardien détérioré"
    if "Guardian_A" in actor:
        return "Gardien à pied"
    if "Guardian_B" in actor:
        return "Gardien tourelle"
    if "Guardian_C" in actor:
        return "Gardien volant"
    if "Guardian_Mini" in actor:
        if "mineure" in previous:
            return "Nano Gardien 2.0 - Épreuve basique de force"
        if "moyenne" in previous:
            return "Nano Gardien 3.0 - Épreuve moyenne de force"
        return "Nano Gardien 4.0 - Épreuve extrême de force"
    if "Keese" in actor:
        if "Electric" in actor:
            return "Chauve-souris électrique"
        if "Fire" in actor:
            return "Chauve-souris de feu"
        if "Ice" in actor:
            return "Chauve-souris de glace"
        return "Chauve-souris"
    if actor == "RemainsFire_Drone_A_01":
        return "Héliss"
    return previous


def enemy_subtype(actor: str, previous: str) -> str:
    names: list[str] = []
    for value in actor.split(", "):
        name = _one_enemy(value, previous)
        if name not in names:
            names.append(name)
    return " / ".join(names)


def normalize_catalog(data: dict) -> dict:
    """Normalise exclusivement les libellés français visibles du catalogue."""
    visible_keys = {
        "name", "label", "region", "subtype", "content_origin_label", "action",
        "completion_condition", "reward", "location", "nearby", "contenu",
        "content",
    }

    def walk(value, key: str | None = None):
        if isinstance(value, dict):
            return {k: walk(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(item, key) for item in value]
        if isinstance(value, str) and key in visible_keys:
            value = DISPLAY_EXACT.get(value, value)
            if key == "region":
                value = REGIONS.get(value, value)
            value = value.replace("fontaine de Malanya", "fontaine de Marlon")
            value = value.replace("nom de Malanya", "nom de Marlon")
            return value
        return value

    normalized = walk(data)
    for layer in normalized.get("map_layers", []):
        if layer.get("layer_type", "").startswith("enemy_") and layer.get("acteur"):
            layer["subtype"] = enemy_subtype(layer["acteur"], layer.get("subtype", ""))
            suffix = re.search(r"\s\d+$", layer.get("name", ""))
            layer["name"] = layer["subtype"] + (suffix.group(0) if suffix else "")
        elif layer.get("layer_type") == "quest_objective":
            layer["subtype"] = DISPLAY_EXACT.get(layer.get("subtype", ""), layer.get("subtype", ""))

    stages = {
        "epreuves-debutant": ("Épreuves basiques de l'épée", "Puissance de l'épée de légende : 40"),
        "epreuves-moyen": ("Épreuves moyennes de l'épée", "Puissance de l'épée de légende : 50"),
        "epreuves-expert": ("Épreuves finales de l'épée", "Puissance permanente de l'épée de légende : 60"),
    }
    for item in normalized.get("trial_of_the_sword", []):
        if item.get("id") in stages:
            item["name"], item["reward"] = stages[item["id"]]
    return normalized