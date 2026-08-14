from __future__ import annotations

import copy
import math
import re
from collections.abc import Iterable

from .guide_enrichment import build_map_guide
from .guides import build_guide
from .localization import localize_editorial_text
from .resources import (load_cartography_reference, load_catalog,
                        load_completion_standard, load_nomenclature_reference,
                        load_runtime_nomenclature_audit, load_solution_reference)


ORIGIN_LABELS = {
    "base": "Jeu de base",
    "amiibo": "Extension amiibo",
    "expansion_bonus": "Bonus de l'Expansion Pass",
    "master_trials": "DLC 1 - Les épreuves légendaires",
    "champions_ballad": "DLC 2 - L'Ode aux Prodiges",
    "master_mode": "Mode expert",
    "free_update": "Mise à jour gratuite Xenoblade Chronicles 2",
}

SHRINE_CHESTS_REMAINING_FILTER = "sanctuaires_termines_coffres_restants"
SHRINE_CHESTS_REMAINING_LABEL = "Sanctuaires terminés - coffres restants"


def _ensure_origin(item: dict) -> None:
    default = "amiibo" if item.get("amiibo") else ("master_trials" if item.get("dlc") else "base")
    origin = item.setdefault("content_origin", default)
    item.setdefault("content_origin_label", ORIGIN_LABELS.get(origin, origin))


def _tracking_id(item: dict) -> str:
    """Public, stable key: independent from save values and catalogue ordering."""
    identity = item.get("id") or item.get("flag") or item.get("name")
    return f"{item.get('categorie', 'element')}:{identity}"


def _apply_solution_reference(catalog: dict) -> dict:
    """Joint les preuves externes sans modifier les identifiants du catalogue."""
    reference = load_solution_reference()
    quest_evidence = reference.get("quests", {})
    quest_facts = reference.get("quest_facts", {})
    for key in ("main_quests", "shrine_quests", "side_quests"):
        for item in catalog.get(key, []):
            evidence = quest_evidence.get(item.get("quest_internal_id"))
            if evidence:
                item["solution_evidence"] = copy.deepcopy(evidence)
            facts = quest_facts.get(item.get("quest_internal_id"))
            if facts:
                localized_facts = copy.deepcopy(facts)
                for field in ("giver", "location", "prerequisite", "reward"):
                    if localized_facts.get(field):
                        localized_facts[field] = localize_editorial_text(localized_facts[field])
                item["quest_facts"] = localized_facts
    stage_by_id = {
        "epreuves-debutant": "beginning",
        "epreuves-moyen": "middle",
        "epreuves-expert": "final",
    }
    for item in catalog.get("trial_of_the_sword", []):
        stage = stage_by_id.get(item.get("id"))
        if stage:
            item["trial_rooms"] = [
                copy.deepcopy(room) for room in reference.get("trial_rooms", [])
                if room.get("stage") == stage
            ]
    catalog["solution_audit"] = copy.deepcopy(reference.get("audit", {}))
    catalog["solution_sources"] = copy.deepcopy(reference.get("sources", []))
    return catalog


def _done(value: object) -> bool:
    return bool(value) and value != -1


def _matches(rule: list[dict], flags: dict[str, object]) -> bool:
    if not rule:
        return False
    return all(flags.get(entry["flag"]) == entry.get("value", True) for entry in rule)


def _item_done(item: dict, flags: dict[str, object]) -> bool:
    if item.get("any_flags"):
        return any(_done(flags.get(flag)) for flag in item["any_flags"])
    if item.get("rule"):
        return _matches(item["rule"], flags)
    flag = item.get("flag")
    if flag and item.get("min_value") is not None:
        value = flags.get(flag, 0)
        return isinstance(value, (int, float)) and value >= item["min_value"]
    return bool(flag and _done(flags.get(flag)))


def _evaluate(items: Iterable[dict], flags: dict[str, object], category: str) -> dict:
    elements, completed, remaining = [], [], []
    for source in items:
        item = dict(source)
        _ensure_origin(item)
        item["categorie"] = category
        if item.get("x") is not None and item.get("z") is not None and not item.get("geo_points"):
            item["geo_points"] = [{
                "role": "objectif", "label": item.get("name", "Objectif"),
                "x": item["x"], "z": item["z"],
            }]
            item.setdefault("location_role", "objectif")
        item["termine"] = _item_done(item, flags)
        item["commence"] = item["termine"] or _matches(item.get("started_rule", []), flags)
        item["statut"] = "terminé" if item["termine"] else ("en cours" if item["commence"] else "à faire")
        if item.get("target") is not None and item.get("flag"):
            item["progression"] = min(int(flags.get(item["flag"], 0) or 0), int(item["target"]))
            item["statut"] = f"{item['progression']}/{item['target']}" if not item["termine"] else "terminé"
        # Les règles sont utiles pour l'audit JSON mais pas dans chaque ligne de l'UI.
        item.pop("rule", None)
        item.pop("started_rule", None)
        elements.append(item)
        (completed if item["termine"] else remaining).append(item)
    return {
        "total": len(elements), "faits": len(completed), "restants": remaining,
        "termines": completed, "elements": elements,
    }


def _evaluate_chests(items: Iterable[dict], flags: dict[str, object]) -> dict:
    report = _evaluate(items, flags, "coffres_sanctuaires")
    for item in report["restants"]:
        shrine_flag = f"Clear_{item['id']}"
        item["sanctuaire_termine"] = _done(flags.get(shrine_flag))
        item["raison"] = (
            "Sanctuaire terminé : coffre encore non validé"
            if item["sanctuaire_termine"] else "Sanctuaire encore non terminé"
        )
    report["manques_dans_sanctuaires_termines"] = sum(
        item.get("sanctuaire_termine", False) for item in report["restants"]
    )
    return report


def _armor_state(item: dict, inventory_ids: set[str], quantities: dict[str, int]) -> dict:
    variants = item.get("variants", [item["id"]])
    owned_levels = [level for level, actor in enumerate(variants) if actor in inventory_ids]
    level = max(owned_levels) if owned_levels else None
    result = dict(item)
    result.update({
        "possede": level is not None,
        "niveau": level,
        "niveau_max": 4,
        "etoiles": "☆☆☆☆" if level is None else "★" * level + "☆" * (4 - level),
    })
    if level is not None and level < 4:
        materials = []
        for material in item.get("recettes", {}).get(str(level + 1), []):
            owned = quantities.get(material["id"], 0)
            required = material["quantity"]
            materials.append({
                **material,
                "possede": owned,
                "requis": required,
                "manque": max(0, required - owned),
                "disponible": owned >= required,
            })
        result["prochaine_amelioration"] = {
            "niveau_cible": level + 1,
            "materiaux": materials,
            "possible": bool(materials) and all(x["disponible"] for x in materials),
        }
    result.pop("variants", None)
    result.pop("recettes", None)
    return result


def _evaluate_armor(items: Iterable[dict], inventory: list[dict] | None, maximal: bool) -> dict:
    inventory = inventory or []
    inventory_ids = {str(entry["id"]) for entry in inventory}
    quantities = {str(entry["id"]): int(entry["quantite"]) for entry in inventory}
    elements, completed, remaining = [], [], []
    for source in items:
        item = _armor_state(source, inventory_ids, quantities)
        _ensure_origin(item)
        item["categorie"] = "armures_max" if maximal else "armures"
        item["termine"] = item["niveau"] == 4 if maximal else item["possede"]
        item["commence"] = item["possede"]
        if maximal:
            item["statut"] = "4 étoiles" if item["termine"] else (
                f"niveau {item['niveau']}/4" if item["possede"] else "à obtenir"
            )
        else:
            item["statut"] = "possédée" if item["termine"] else "à obtenir"
        elements.append(item)
        (completed if item["termine"] else remaining).append(item)
    return {
        "total": len(elements), "faits": len(completed), "restants": remaining,
        "termines": completed, "elements": elements,
    }


def _evaluate_inventory_items(items: Iterable[dict], inventory: list[dict] | None,
                              category: str) -> dict:
    inventory_ids = {str(entry["id"]) for entry in (inventory or [])}
    elements, completed, remaining = [], [], []
    for source in items:
        item = dict(source)
        _ensure_origin(item)
        variants = item.pop("variants", [item["id"]])
        item["categorie"] = category
        item["possede"] = any(actor in inventory_ids for actor in variants)
        item["termine"] = item["possede"]
        item["commence"] = item["possede"]
        item["statut"] = "possédé" if item["possede"] else "à obtenir"
        if item.get("x") is not None and item.get("z") is not None:
            item["geo_points"] = [{"role": "obtention", "label": item["name"],
                                   "x": item["x"], "z": item["z"]}]
        elements.append(item)
        (completed if item["termine"] else remaining).append(item)
    return {"total": len(elements), "faits": len(completed), "restants": remaining,
            "termines": completed, "elements": elements}


def _evaluate_dlc_features(items: Iterable[dict], flags: dict[str, object]) -> dict:
    dlc_available = any(_done(flags.get(flag)) for flag in (
        "BalladOfHeroes_Activated", "100enemy_Activated", "IsGet_Obj_Motorcycle",
        "IsGet_Obj_WarpDLC", "TreasureHunt_Aoc1_RunAutoOrder", "TreasureHunt_Aoc2_RunAutoOrder",
    )) or int(flags.get("AoCVerAtLastPlay", 0) or 0) > 0
    elements, completed, remaining = [], [], []
    for source in items:
        item = dict(source)
        _ensure_origin(item)
        used = any(_done(flags.get(flag)) for flag in item.get("usage_flags", []))
        item.update({
            "categorie": "fonctionnalites_dlc", "disponible": dlc_available,
            "utilise": used, "termine": dlc_available, "commence": used,
            "statut": ("active dans cette sauvegarde" if used else
                       "disponible - sauvegarde distincte" if item.get("separate_save") else
                       "disponible dans l'interface de la carte") if dlc_available else
                      "Expansion Pass non détecté",
        })
        item.pop("usage_flags", None)
        elements.append(item)
        (completed if item["termine"] else remaining).append(item)
    return {"total": len(elements), "faits": len(completed), "restants": remaining,
            "termines": completed, "elements": elements}


FILTER_GROUP_LABELS = {
    "voyage": "Voyage et lieux",
    "quetes": "Quêtes et souvenirs",
    "tresors": "Trésors",
    "collections": "Collections et équipement",
    "monstres": "Monstres et farm",
    "bosses": "Boss et victoires permanentes",
    "dlc": "Expansion Pass et contenus additionnels",
    "progression": "Progression permanente",
    "services": "Services et points utiles",
    "manuel": "Objectifs à valider manuellement",
}

FILTER_GROUP_ORDER = tuple(FILTER_GROUP_LABELS)

TREASURE_FILTER_LABELS = {
    "coffre_unique": "Objets uniques", "coffre_vetement": "Vêtements",
    "coffre_arc": "Arcs", "coffre_bouclier": "Boucliers", "coffre_lance": "Lances",
    "coffre_baguette": "Baguettes", "coffre_arme_deux_mains": "Armes à deux mains",
    "coffre_arme_une_main": "Armes à une main", "coffre_fleche": "Flèches",
    "coffre_gemme_rare": "Gemmes rares", "coffre_gemme_commune": "Gemmes communes",
    "coffre_gros_rubis": "Gros rubis", "coffre_petit_rubis": "Petits rubis",
    "coffre_materiau": "Matériaux", "coffre_autre": "Autres coffres",
}

CATEGORY_FILTERS = {
    "sanctuaires": ("voyage", "sanctuaires", "Sanctuaires"),
    "tours": ("voyage", "tours", "Tours Sheikah"),
    "lieux": ("voyage", "lieux", "Lieux nommés"),
    "quetes_principales": ("quetes", "quetes_principales", "Quêtes principales"),
    "quetes_sanctuaires": ("quetes", "quetes_sanctuaires", "Quêtes de sanctuaire"),
    "quetes_secondaires": ("quetes", "quetes_secondaires", "Quêtes secondaires"),
    "souvenirs": ("quetes", "souvenirs", "Souvenirs"),
    "korogus": ("collections", "korogus", "Korogus"),
    "compendium": ("collections", "compendium", "Compendium"),
    "armures": ("collections", "armures", "Armures possédées"),
    "armures_max": ("collections", "armures_max", "Armures 4 étoiles"),
    "equipements_particuliers": ("collections", "equipements_particuliers", "Équipements particuliers"),
    "harnachements": ("collections", "harnachements", "Filets et selles"),
    "hinox": ("bosses", "hinox", "Hinox et Stalhinox"),
    "talus": ("bosses", "talus", "Lithoroks"),
    "moldarquors": ("bosses", "moldarquors", "Moldarquors"),
    "creatures_divines": ("bosses", "creatures_divines", "Créatures divines"),
    "bosses_scenarises": ("bosses", "bosses_scenarises", "Boss scénarisés et DLC"),
    "grandes_fees": ("progression", "grandes_fees", "Grandes Fées"),
    "malanya": ("progression", "malanya", "Marlon"),
    "epreuves_epee": ("progression", "epreuves_epee", "Épreuves de l'épée"),
    "medailles_kilton": ("progression", "medailles_kilton", "Médailles de Kilton"),
    "recompenses_uniques": ("progression", "recompenses_uniques", "Récompenses uniques"),
    "objets_speciaux": ("progression", "objets_speciaux", "Objets spéciaux et DLC"),
    "bonus_expansion": ("dlc", "bonus_expansion", "Trois coffres bonus de l'Expansion Pass"),
    "ameliorations_prodiges": ("dlc", "ameliorations_prodiges", "Pouvoirs des Prodiges +"),
    "fonctionnalites_dlc": ("dlc", "fonctionnalites_dlc", "Mode Empreintes et mode Expert"),
    "tresors_chiens": ("manuel", "tresors_chiens", "Trésors indiqués par les chiens"),
}

# Contrat indépendant du catalogue courant : une variation doit être examinée
# et acceptée explicitement au lieu de modifier silencieusement un compteur.
FILTER_EXPECTED_COUNTS = {
    "laboratoires": 2, "lieux": 168, "sanctuaires": 136, "tours": 15,
    "objectifs_quete": 77, "quetes_sanctuaires": 42, "quetes_principales": 20,
    "quetes_secondaires": 90, "souvenirs": 23,
    "coffre_arc": 141, "coffre_arme_deux_mains": 72, "coffre_arme_une_main": 119,
    "coffre_autre": 5, "coffre_baguette": 16, "coffre_bouclier": 79,
    "coffre_fleche": 325, "coffre_gemme_commune": 152, "coffre_gemme_rare": 160,
    "coffre_gros_rubis": 272, "coffre_lance": 94, "coffre_materiau": 46,
    "coffre_unique": 15, "coffre_petit_rubis": 6, "coffre_vetement": 37,
    "armures_max": 67, "armures": 67, "compendium": 394, "harnachements": 12,
    "korogus": 900, "equipements_particuliers": 40,
    "bokoblins": 1176, "chauves_souris": 372, "chuchus": 459, "gardiens": 154,
    "hinox_farm": 40, "sentinelles": 18, "lithoroks_farm": 41, "lynels": 23,
    "lezalfos": 729, "moblins": 276, "moldarquors_farm": 5,
    "nano_gardiens": 21, "octos": 227, "octos_aeriens": 600,
    "petits_lithoroks": 272, "sorciers": 56, "yigas": 20,
    "bosses_scenarises": 13, "creatures_divines": 4, "hinox": 40,
    "talus": 40, "moldarquors": 4,
    "fonctionnalites_dlc": 2, "ameliorations_prodiges": 4, "bonus_expansion": 3,
    "grandes_fees": 1, "malanya": 1, "medailles_kilton": 3,
    "objets_speciaux": 2, "recompenses_uniques": 2, "epreuves_epee": 3,
    "auberges": 7, "bijouteries": 1, "boutiques_armures": 5,
    "fontaine_malanya": 1, "fontaines_grandes_fees": 4, "kilton": 8,
    "magasins_generaux": 5, "marmites": 114, "radeaux": 46, "relais": 15,
    "statues_deesse": 20, "villages": 8, "tresors_chiens": 15,
}

NO_NATURAL_LOCATION_CATEGORIES = {
    "armures", "armures_max", "compendium", "fonctionnalites_dlc",
    "ameliorations_prodiges", "medailles_kilton", "recompenses_uniques",
}

SCRIPTED_CATEGORIES = {
    "quetes_principales", "quetes_sanctuaires", "quetes_secondaires", "souvenirs",
    "creatures_divines", "bosses_scenarises", "epreuves_epee",
}

PLACEMENT_LABELS = {
    "fixed_confirmed": "Placement fixe confirmé",
    "scripted": "Rencontre ou objectif scénarisé",
    "dynamic_unmapped": "Apparition dynamique non cartographiable exhaustivement",
    "non_spatial": "Collection sans localisation naturelle unique",
    "interior_confirmed": "Position intérieure confirmée dans les données du jeu",
}


def _apply_cartography_reference(catalog: dict) -> dict:
    """Ajoute les cartes intérieures et les positions d'obtention sans inventer un point Hyrule."""
    reference = load_cartography_reference()
    for item in catalog.get("shrine_chests", []):
        item.update(copy.deepcopy(reference["shrines"][item["id"]]))
        contents = [chest["content"] for chest in item["interior_chests"]]
        item["contents"] = contents
        item["contenu"] = " ; ".join(contents)
    shrine_maps = {
        item["id"]: {
            "interior_map": item.get("interior_map"),
            "interior_map_label": item.get("interior_map_label"),
            "interior_bounds": copy.deepcopy(item.get("interior_bounds")),
            "interior_chests": copy.deepcopy(item.get("interior_chests", [])),
            "chest_count": item.get("chest_count", 0),
            "chest_contents": copy.deepcopy(item.get("contents", [])),
        }
        for item in catalog.get("shrine_chests", [])
    }
    for shrine in catalog.get("shrines", []):
        shrine.update(shrine_maps.get(shrine.get("id"), {}))
    for item in catalog.get("world_chests", []):
        interior = reference["trial_chests"].get(str(item["hash"]))
        if interior:
            item.update(copy.deepcopy(interior))
    for item in catalog.get("dungeon_chests", []):
        item.update(copy.deepcopy(reference["dungeon_chests"][str(item["hash"])]))

    # Les activités intérieures sont placées à leur accès réel sur Hyrule.
    activity_points = {
        "epreuves-debutant": (431.66, -2110.99, "Piédestal de l'Épée de légende - Forêt Korogu"),
        "epreuves-moyen": (431.66, -2110.99, "Piédestal de l'Épée de légende - Forêt Korogu"),
        "epreuves-expert": (431.66, -2110.99, "Piédestal de l'Épée de légende - Forêt Korogu"),
    }
    for item in catalog.get("trial_of_the_sword", []):
        item["x"], item["z"], item["nearby"] = activity_points[item["id"]]
        item["location_role"] = "entrée de l'activité"
    for item in catalog.get("scripted_bosses", []):
        if item["id"] == "miz-kyosia":
            item.update(x=-1102.23, z=1880.13, nearby="Sanctuaire de la Renaissance",
                        location_role="entrée de l'Épreuve finale")
    for item in catalog.get("special_items", []):
        if item["id"] == "destrier-zero-un":
            item.update(x=-1102.23, z=1880.13, nearby="Sanctuaire de la Renaissance",
                        location_role="lieu d'obtention")

    gear_points = {
        "filet-royal": (-1449.49, 1269.01, "Relais de l'Orée de la Plaine"),
        "selle-royale": (-1449.49, 1269.01, "Relais de l'Orée de la Plaine"),
        "filet-chevalier": (-231.20, 3259.88, "Camp d'archerie montée"),
        "selle-chevalier": (-231.20, 3259.88, "Camp d'archerie montée"),
        "filet-extravagant": (529.25, 3462.80, "Relais des Alpages - parcours d'obstacles"),
        "selle-extravagante": (529.25, 3462.80, "Relais des Alpages - parcours d'obstacles"),
    }
    non_spatial_gear = {"filet-voyageur", "selle-voyageur", "filet-monstre", "selle-monstre"}
    for item in catalog.get("horse_gear", []):
        if item["id"] in gear_points:
            item["x"], item["z"], item["nearby"] = gear_points[item["id"]]
            item["location_role"] = "lieu d'obtention"
        elif item["id"] in non_spatial_gear:
            item["natural_location_absent"] = True
            item["location_explanation"] = (
                "Récompense amiibo aléatoire" if item.get("content_origin") == "amiibo"
                else "Objet vendu par Kilton dans plusieurs boutiques nocturnes"
            )

    gerudo = {"Armor_053_Head", "Armor_053_Lower", "Armor_053_Upper"}
    for item in catalog.get("special_armor", []):
        if item["id"] in gerudo:
            item.update(x=-3861.0, z=2885.0, nearby="Cité Gerudo",
                        location_role="lieu d'achat")
        elif item.get("x") is None or item.get("z") is None:
            item["natural_location_absent"] = True
            item["location_explanation"] = (
                "Récompense amiibo aléatoire" if item.get("content_origin") == "amiibo"
                else "Objet vendu par Kilton dans plusieurs boutiques nocturnes"
            )
    catalog["cartography_audit"] = reference["audit"]
    catalog["cartography_sources"] = reference["sources"]
    return catalog


def _enrich_service_names(catalog: dict) -> None:
    """Remplace les numéros techniques par un service et son repère géographique le plus proche."""
    labels = {
        "statue_deesse": "Statue de la Déesse", "marmite": "Marmite", "radeau": "Radeau",
        "kilton": "Boutique de Kilton", "auberge": "Auberge",
        "boutique_armures": "Boutique d'armures", "magasin_general": "Magasin général",
        "bijouterie": "Bijouterie",
    }
    anchors = [item for item in [*catalog.get("locations", []), *catalog.get("map_layers", [])]
               if item.get("x") is not None and item.get("z") is not None
               and (item in catalog.get("locations", []) or item.get("layer_type") in {
                   "relais", "village", "laboratoire", "grande_fee", "malanya"
               })]
    for item in catalog.get("map_layers", []):
        kind = item.get("layer_type")
        if kind not in labels or not re.search(r" \d+$", item.get("name", "")):
            continue
        nearest = min(anchors, key=lambda anchor: math.hypot(
            item["x"] - anchor["x"], item["z"] - anchor["z"]))
        distance = round(math.hypot(item["x"] - nearest["x"], item["z"] - nearest["z"]))
        item["technical_name"] = item["name"]
        item["name"] = f"{labels[kind]} - {nearest['name']}"
        item["nearby"] = nearest["name"]
        item["nearby_distance_m"] = distance
    boss_groups = {
        "hinoxes": "Hinox", "taluses": "Lithorok", "moldugas": "Moldarquor",
    }
    for group, label in boss_groups.items():
        for item in catalog.get(group, []):
            if not re.search(r" \d+$", item.get("name", "")):
                continue
            nearest = min(anchors, key=lambda anchor: math.hypot(
                item["x"] - anchor["x"], item["z"] - anchor["z"]))
            distance = round(math.hypot(item["x"] - nearest["x"], item["z"] - nearest["z"]))
            item["technical_name"] = item["name"]
            item["name"] = f"{label} - près de {nearest['name']}"
            item["nearby"] = nearest["name"]
            item["nearby_distance_m"] = distance


def _scope_metadata(item: dict) -> None:
    """Décrit honnêtement où et dans quel mode un élément peut être affiché."""
    category = item.get("categorie", "")
    layer_type = item.get("layer_type", "")
    located = item.get("x") is not None and item.get("z") is not None
    expert_only = bool(item.get("mode_expert")) or item.get("content_origin") == "master_mode"
    item["game_mode_scope"] = "expert_only" if expert_only else "all_modes"
    item["game_mode_label"] = "Exclusif au mode Expert" if expert_only else "Modes normal et Expert"
    item["display_scope"] = "map_and_list" if located else "list_only"
    if located:
        item["location_status"] = "located"
        item["location_status_label"] = "Coordonnées confirmées"
    elif item.get("interior_map"):
        item["display_scope"] = "interior_only"
        item["location_status"] = "interior_coordinates"
        item["location_status_label"] = "Coordonnées de carte intérieure confirmées"
    elif category in NO_NATURAL_LOCATION_CATEGORIES or item.get("natural_location_absent"):
        item["location_status"] = "no_natural_location"
        item["location_status_label"] = "Sans localisation naturelle"
    else:
        item["location_status"] = "coordinates_missing"
        item["location_status_label"] = "Coordonnées non renseignées"

    if layer_type == "enemy_yiga":
        item.update({
            "placement_kind": "fixed_confirmed",
            "coverage_scope": "confirmed_subset",
            "coverage_label": "Placements fixes uniquement - rencontres dynamiques exclues",
            "coverage_note": (
                "Ce point appartient aux placements fixes du jeu. Les Yigas générés "
                "dynamiquement par AutoPlacementMgr n'ont pas de coordonnées stables "
                "et ne sont pas prétendus exhaustifs."
            ),
        })
    elif layer_type in {"enemy_sentry", "enemy_guardian_scout", "quest_objective"}:
        item.update({
            "placement_kind": "scripted", "coverage_scope": "fixed_confirmed",
            "coverage_label": "Placements scénarisés confirmés",
        })
    elif layer_type:
        item.update({
            "placement_kind": "fixed_confirmed", "coverage_scope": "fixed_confirmed",
            "coverage_label": "Placements fixes confirmés dans les données du jeu",
        })
    elif item.get("interior_map") and not located:
        item.update({
            "placement_kind": "interior_confirmed", "coverage_scope": "fixed_confirmed",
            "coverage_label": "Position confirmée sur une carte intérieure du jeu",
        })
    elif (category in NO_NATURAL_LOCATION_CATEGORIES or item.get("natural_location_absent")) and not located:
        item.update({
            "placement_kind": "non_spatial", "coverage_scope": "catalog_complete",
            "coverage_label": "Collection filtrable dans la liste",
        })
    elif category in SCRIPTED_CATEGORIES:
        item.update({
            "placement_kind": "scripted", "coverage_scope": "catalog_complete",
            "coverage_label": "Objectif scénarisé du catalogue",
        })
    else:
        item.update({
            "placement_kind": "fixed_confirmed", "coverage_scope": "catalog_complete",
            "coverage_label": "Objectif du catalogue",
        })
    item["placement_label"] = PLACEMENT_LABELS[item["placement_kind"]]
    if item.get("farm"):
        item["activity_scope"] = "repeatable_farm"
        item["activity_scope_label"] = "Activité répétable - réapparition à la lune de sang"
    elif category in {"hinox", "talus", "moldarquors"}:
        item["activity_scope"] = "permanent_victory"
        item["activity_scope_label"] = "Victoire permanente distincte du point de farm"
    elif item.get("informational"):
        item["activity_scope"] = "informational"
        item["activity_scope_label"] = "Point informatif"
    else:
        item["activity_scope"] = "permanent_objective"
        item["activity_scope_label"] = "Objectif permanent"


def _manual_dog_treasures(catalog: dict) -> list[dict]:
    positions = {
        item.get("name"): (item.get("x"), item.get("z"))
        for item in [*catalog.get("map_layers", []), *catalog.get("locations", [])]
        if item.get("name")
    }
    result = []
    for index, source in enumerate(catalog.get("manual", {}).get("chiens", []), 1):
        item = dict(source)
        item.update({
            "id": f"tresor-chien-{index:02d}",
            "name": f"Trésor du chien - {item['location']}",
            "reward": f"{item.get('item_qty', 1)} × {item['item']}",
            "content_origin": "base", "manual_only": True,
        })
        x, z = positions.get(item["location"], (None, None))
        if x is not None and z is not None:
            item.update(x=x, z=z, nearby=item["location"])
        result.append(item)
    return result


def _evaluate_manual(items: Iterable[dict], category: str) -> dict:
    elements = []
    for source in items:
        item = dict(source)
        _ensure_origin(item)
        item.update({
            "categorie": category, "termine": False, "commence": False,
            "statut": "à valider manuellement", "detection": "suivi manuel local",
        })
        if item.get("x") is not None and item.get("z") is not None:
            item["geo_points"] = [{"role": "objectif", "label": item["name"],
                                   "x": item["x"], "z": item["z"]}]
        elements.append(item)
    return {"total": len(elements), "faits": 0, "restants": list(elements),
            "termines": [], "elements": elements}


def _treasure_filter(item: dict) -> tuple[str, str]:
    text = f"{item.get('name', '')} {item.get('contenu', '')}".lower()
    rules = (
        (("royal guard", "garde royal", "master sword", "épée de légende", "travel medallion", "amulette de téléportation", "maracas de noïa", "sept joyaux"), "unique", "Objets uniques"),
        (("armor", "shirt", "tunic", "trousers", "boots", "helmet", "helm", "mask", "armure", "tunique", "pantalon", "bottes", "casque", "masque", "grèves", "coiffe", "culotte", "couronne", "cagoule", "collant", "combinaison", "maillot", "doublet", "gilet", "bandana", "gants", "souliers"), "vetement", "Vêtements"),
        (("bow", "arc"), "arc", "Arcs"),
        (("shield", "bouclier"), "bouclier", "Boucliers"),
        (("spear", "lance", "halberd", "hallebarde", "trident", "javelot", "harpon", "fourche"), "lance", "Lances"),
        (("rod", "baguette"), "baguette", "Baguettes"),
        (("claymore", "greatsword", "crusher", "espadon", "brise-montagne", "grand boomerang", "hache", "masse", "marteau", "brise-roc", "casse-pierre", "massue"), "arme_deux_mains", "Armes à deux mains"),
        (("sword", "broadsword", "blade", "sabre", "épée", "glaive", "boomerang", "cimeterre", "lame", "serpe", "torche", "eventail", "éventail"), "arme_une_main", "Armes à une main"),
        (("arrow", "flèche"), "fleche", "Flèches"),
        (("diamond", "ruby", "sapphire", "topaz", "diamant", "rubis brut", "saphir", "topaze"), "gemme_rare", "Gemmes rares"),
        (("amber", "opal", "ambre", "opale", "luminous stone", "gemme nox"), "gemme_commune", "Gemmes communes"),
        (("purple rupee", "silver rupee", "gold rupee", "rubis violet", "rubis argenté", "rubis doré"), "gros_rubis", "Gros rubis"),
        (("rupee", "rubis vert", "rubis bleu", "rubis rouge"), "petit_rubis", "Petits rubis"),
        (("ore", "wood", "food", "elixir", "material", "minerai", "bois", "aliment", "remède", "matériau", "fragment d'étoile", "silex", "antique", "écaille", "éclat de croc", "banane"), "materiau", "Matériaux"),
    )
    for needles, type_id, label in rules:
        if any(needle in text for needle in needles):
            return f"coffre_{type_id}", label
    return "coffre_autre", "Autres coffres"


def _apply_filter_metadata(item: dict, category: str) -> None:
    if category in {"coffres_sanctuaires", "coffres_monde", "coffres_donjons"}:
        type_id, label = _treasure_filter(item)
        item.update({"filter_group": "tresors", "filter_type": type_id, "filter_label": label})
        content_filter_types = set()
        if item.get("contents"):
            content_filter_types.update({
                _treasure_filter({"contenu": content})[0] for content in item["contents"]
            } - {"coffre_autre"})
        if (category == "coffres_sanctuaires"
                and item.get("sanctuaire_termine")
                and not item.get("termine")):
            content_filter_types.add(SHRINE_CHESTS_REMAINING_FILTER)
        if content_filter_types:
            item["content_filter_types"] = sorted(content_filter_types)
        return
    group, type_id, label = CATEGORY_FILTERS[category]
    item.update({"filter_group": group, "filter_type": type_id, "filter_label": label})


def _prepare_map_layers(items: Iterable[dict]) -> list[dict]:
    labels = {
        "enemy_bokoblin": ("monstres", "bokoblins", "Bokoblins"),
        "enemy_moblin": ("monstres", "moblins", "Moblins"),
        "enemy_lizalfos": ("monstres", "lezalfos", "Lézalfos"),
        "enemy_chuchu": ("monstres", "chuchus", "Chuchus"),
        "enemy_keese": ("monstres", "chauves_souris", "Chauves-souris"),
        "enemy_octorok": ("monstres", "octos", "Octos"),
        "enemy_sky_octorok": ("monstres", "octos_aeriens", "Octos aériens - mode expert"),
        "enemy_wizzrobe": ("monstres", "sorciers", "Sorciers"),
        "enemy_yiga": ("monstres", "yigas", "Yigas fixes"),
        "enemy_lynel": ("monstres", "lynels", "Lynels"),
        "enemy_guardian": ("monstres", "gardiens", "Gardiens"),
        "enemy_guardian_scout": ("monstres", "nano_gardiens", "Nano Gardiens des sanctuaires"),
        "enemy_hinox": ("monstres", "hinox_farm", "Hinox et Stalhinox - farm"),
        "enemy_talus": ("monstres", "lithoroks_farm", "Lithoroks - farm"),
        "enemy_pebblit": ("monstres", "petits_lithoroks", "Petits Lithoroks"),
        "enemy_molduga": ("monstres", "moldarquors_farm", "Moldarquors - farm"),
        "enemy_sentry": ("monstres", "sentinelles", "Héliss de Vah'Rudania"),
        "relais": ("services", "relais", "Relais"),
        "village": ("services", "villages", "Villages et cités"),
        "laboratoire": ("voyage", "laboratoires", "Laboratoires antiques"),
        "grande_fee": ("services", "fontaines_grandes_fees", "Fontaines des Grandes Fées"),
        "malanya": ("services", "fontaine_malanya", "Fontaine de Marlon"),
        "statue_deesse": ("services", "statues_deesse", "Statues de la Déesse"),
        "marmite": ("services", "marmites", "Marmites"),
        "radeau": ("services", "radeaux", "Radeaux"),
        "kilton": ("services", "kilton", "Kilton"),
        "auberge": ("services", "auberges", "Auberges"),
        "boutique_armures": ("services", "boutiques_armures", "Boutiques d'armures"),
        "magasin_general": ("services", "magasins_generaux", "Magasins généraux"),
        "bijouterie": ("services", "bijouteries", "Bijouteries"),
        "quest_objective": ("quetes", "objectifs_quete", "Objectifs et destinations de quête"),
    }
    result = []
    for source in items:
        item = dict(source)
        _ensure_origin(item)
        group, type_id, label = labels[item["layer_type"]]
        item.update({
            "categorie": "informations_carte", "filter_group": group,
            "filter_type": type_id, "filter_label": label,
            "termine": False, "commence": False, "statut": "informatif",
        })
        if item.get("repeatable"):
            item["statut"] = "réapparaît après une lune de sang"
            item["farm"] = True
        if item.get("x") is not None and item.get("z") is not None:
            item["geo_points"] = [{"role": "position", "label": item["name"],
                                   "x": item["x"], "z": item["z"]}]
        _scope_metadata(item)
        item["guide"] = build_map_guide(item)
        result.append(item)
    return result


def _filter_groups(items: Iterable[dict]) -> list[dict]:
    buckets: dict[tuple[str, str, str], list[dict]] = {}
    for item in items:
        key = (item["filter_group"], item["filter_type"], item["filter_label"])
        buckets.setdefault(key, []).append(item)
        if SHRINE_CHESTS_REMAINING_FILTER in item.get("content_filter_types", []):
            special_key = (
                "tresors",
                SHRINE_CHESTS_REMAINING_FILTER,
                SHRINE_CHESTS_REMAINING_LABEL,
            )
            buckets.setdefault(special_key, []).append(item)
    groups = []
    for group_id in FILTER_GROUP_ORDER:
        types = [
            {
                "id": type_id, "label": label, "count": len(entries),
                "expected_count": FILTER_EXPECTED_COUNTS.get(type_id),
                "count_matches_reference": (
                    FILTER_EXPECTED_COUNTS.get(type_id) is None
                    or len(entries) == FILTER_EXPECTED_COUNTS[type_id]
                ),
                "map_count": sum(item["display_scope"] == "map_and_list" for item in entries),
                "list_only_count": sum(item["display_scope"] == "list_only" for item in entries),
                "interior_count": sum(item["display_scope"] == "interior_only" for item in entries),
                "expert_only_count": sum(item["game_mode_scope"] == "expert_only" for item in entries),
                "normal_default_count": sum(item["game_mode_scope"] != "expert_only" for item in entries),
                "placement_kinds": sorted({item["placement_kind"] for item in entries}),
                "coverage_scopes": sorted({item["coverage_scope"] for item in entries}),
            }
            for (candidate_group, type_id, label), entries in buckets.items()
            if candidate_group == group_id
        ]
        types.sort(key=lambda item: item["label"])
        if types:
            groups.append({"id": group_id, "label": FILTER_GROUP_LABELS[group_id],
                           "count": sum(item["count"] for item in types), "types": types})
    return groups


def _filter_scope_audit(items: list[dict], groups: list[dict], save_mode: str) -> dict:
    monster_types = []
    for group in groups:
        if group["id"] != "monstres":
            continue
        for item in group["types"]:
            monster_types.append({
                **item,
                "claim": (
                    "Sous-ensemble fixe confirmé ; les apparitions dynamiques ne sont pas incluses."
                    if item["id"] == "yigas" else
                    "Placements fixes confirmés de cette famille dans la source cartographique."
                ),
            })
    expert_only = [item for item in items if item["game_mode_scope"] == "expert_only"]
    located = [item for item in items if item["display_scope"] == "map_and_list"]
    missing = [item for item in items if item["location_status"] == "coordinates_missing"]
    natural = [item for item in items if item["location_status"] == "no_natural_location"]
    interior = [item for item in items if item["display_scope"] == "interior_only"]
    list_only = [item for item in items if item["display_scope"] == "list_only"]
    mismatches = [item for group in groups for item in group["types"]
                  if not item["count_matches_reference"]]
    default_visible = [item for item in items
                       if save_mode == "expert" or item["game_mode_scope"] != "expert_only"]
    return {
        "schema_version": 1,
        "status": "complete" if not mismatches else "mismatch",
        "save_mode": save_mode,
        "default_mode_filter": "expert" if save_mode == "expert" else "normal",
        "counts": {
            "all_items": len(items), "default_visible": len(default_visible),
            "expert_only": len(expert_only), "map_and_list": len(located),
            "list_only": len(list_only), "interior_only": len(interior),
            "coordinates_missing": len(missing),
            "no_natural_location": len(natural),
            "filter_types": sum(len(group["types"]) for group in groups),
        },
        "reference_mismatches": mismatches,
        "monster_types": monster_types,
        "dynamic_limitations": [{
            "id": "yigas_dynamiques", "label": "Rencontres dynamiques de Yigas",
            "placement_kind": "dynamic_unmapped", "mapped_count": 0,
            "claim": (
                "AutoPlacementMgr choisit les apparitions selon la zone et l'état de la quête ; "
                "elles n'ont pas de coordonnées permanentes et sont volontairement exclues."
            ),
            "source_url": "https://zeldamods.org/wiki/Yiga_Clan_member_spawns",
        }],
        "rules": [
            "Le mode de la sauvegarde détermine l'affichage initial.",
            "Le réglage Tous les modes permet d'afficher volontairement les exclusivités Expert.",
            "Un point de farm reste visible après une victoire et réapparaît à la lune de sang.",
            "Les objectifs permanents et les activités répétables utilisent des portées distinctes.",
            "Une absence de coordonnées est distinguée d'une collection sans localisation naturelle.",
        ],
    }


def _cartography_quality_audit(items: list[dict], catalog_audit: dict) -> dict:
    """Contrôles reproductibles des positions publiques et intérieures."""
    invalid_world = []
    incomplete_pairs = []
    invalid_interior = []
    identities: set[tuple] = set()
    duplicate_identities = []
    for item in items:
        x, z = item.get("x"), item.get("z")
        if (x is None) != (z is None):
            incomplete_pairs.append(item.get("tracking_id"))
        elif x is not None and (not isinstance(x, (int, float)) or not isinstance(z, (int, float))
                                or not math.isfinite(x) or not math.isfinite(z)
                                or abs(x) > 6000 or abs(z) > 5000):
            invalid_world.append(item.get("tracking_id"))
        identity = (item.get("categorie"), item.get("id"), item.get("hash"), item.get("flag"))
        if identity in identities:
            duplicate_identities.append(item.get("tracking_id"))
        identities.add(identity)
        interior = item.get("interior_chests", [])
        if item.get("interior_position"):
            interior = [item["interior_position"]]
        for point in interior:
            coords = [point.get(axis) for axis in ("x", "y", "z")]
            if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in coords):
                invalid_interior.append(item.get("tracking_id"))
    unexplained = [item.get("tracking_id") for item in items
                   if item.get("location_status") == "coordinates_missing"]
    issues = invalid_world + incomplete_pairs + invalid_interior + duplicate_identities + unexplained
    return {
        "schema_version": 1, "status": "complete" if not issues else "issues",
        **catalog_audit,
        "world_coordinates_checked": sum(item.get("x") is not None for item in items),
        "interior_entries_checked": sum(item.get("display_scope") == "interior_only" for item in items),
        "invalid_world_coordinates": invalid_world,
        "incomplete_coordinate_pairs": incomplete_pairs,
        "invalid_interior_coordinates": invalid_interior,
        "duplicate_stable_identities": duplicate_identities,
        "unexplained_missing_coordinates": unexplained,
    }


def _official_map(catalog: dict, flags: dict[str, object]) -> dict:
    """Reproduit le compteur de carte, séparé de l'indice de couverture."""
    dlc_evidence = any(
        _done(flags.get(f"Location_Dungeon{number:03d}")) for number in range(120, 137)
    ) or any(_done(flags.get(flag)) for flag in (
        "BalladOfHeroes_Activated", "100enemy_Activated", "IsGet_Obj_WarpDLC",
        "IsGet_Obj_Motorcycle",
    ))
    base_components = {
        "korogus": {
            "faits": sum(_item_done(item, flags) for item in catalog["koroks"]),
            "total": 900,
        },
        "sanctuaires_base": {
            "faits": sum(_done(flags.get(f"Location_Dungeon{number:03d}")) for number in range(120)),
            "total": 120,
        },
        "marqueurs_carte": {
            "faits": sum(_done(flags.get(item["flag"])) for item in catalog["official_map_locations"]),
            "total": 187,
        },
    }
    dlc_components = {
        **base_components,
        "sanctuaires_dlc": {
            "faits": sum(_done(flags.get(f"Location_Dungeon{number:03d}")) for number in range(120, 136)),
            "total": 16,
        },
        "donjon_final_dlc": {
            "faits": int(_done(flags.get("Location_Dungeon136"))), "total": 1,
        },
    }

    def scenario(mode: str, components: dict[str, dict[str, int]]) -> dict:
        done = sum(item["faits"] for item in components.values())
        total = sum(item["total"] for item in components.values())
        percent = 100 * done / total
        return {
            "mode": mode, "faits": done, "total": total,
            "pourcentage": round(percent, 2), "pourcentage_affiche": f"{percent:.2f} %",
            "valeur_par_marqueur": 100 / total, "components": components,
        }

    scenarios = {"base": scenario("base", base_components), "dlc": scenario("dlc", dlc_components)}
    selected_mode = "dlc" if dlc_evidence else "base"
    return {
        **scenarios[selected_mode],
        "selected_mode": selected_mode,
        "selection": "automatique",
        "scenarios": scenarios,
        "override_modes": ["automatique", "base", "dlc"],
        "dlc_detecte": dlc_evidence,
        "detection_dlc": "progression DLC présente dans la sauvegarde" if dlc_evidence else
                         "aucune progression DLC détectée ; formule jeu de base sélectionnée automatiquement",
        "visible_dans_le_jeu": _done(flags.get("GanonQuest_Finished")),
        "condition_affichage": "Le jeu affiche ce compteur après la première victoire contre Ganon.",
        "note": "Compteur de carte officiel : chaque marqueur a le même poids. Les quêtes, coffres, souvenirs et le compendium n'y participent pas.",
    }


def _completion_reference(standard: dict, categories: dict, all_items: list[dict],
                          official_map: dict, manual_required: list[dict],
                          save_context: dict | None = None) -> dict:
    """Dérive les statuts et profils depuis le rapport au lieu d'un état figé."""
    resolved = []
    for source in standard["categories"]:
        item = dict(source)
        item.pop("current_status", None)
        refs = ([item["report_category"]] if item.get("report_category") else
                list(item.get("report_categories", [])))
        if item["inclusion"] == "informational":
            status = "informational"
        elif refs:
            status = "complete" if all(ref in categories and categories[ref]["total"] > 0 for ref in refs) else "missing"
        elif item["id"] == "donjon_final_dlc":
            status = "complete" if "dlc" in official_map["scenarios"] else "missing"
        elif item["id"] == "amiibo":
            status = "complete" if any(value.get("content_origin") == "amiibo" for value in all_items) else "missing"
        else:
            status = "missing"
        item["current_status"] = status
        resolved.append(item)

    required_incomplete = sum(
        item["inclusion"] == "required" and item["current_status"] != "complete"
        for item in resolved
    )
    status_counts = {
        status: sum(item["current_status"] == status for item in resolved)
        for status in standard["statuses"]
    }
    scored_items = [
        item for category in categories.values() if not category["score_excluded"]
        for item in category["elements"]
    ]
    base_items = [item for item in scored_items if item.get("content_origin", "base") == "base"]
    dlc_origins = {"base", "expansion_bonus", "master_trials", "champions_ballad", "free_update"}
    dlc_items = [item for item in scored_items if item.get("content_origin", "base") in dlc_origins]
    amiibo_items = [item for item in all_items if item.get("content_origin") == "amiibo"]
    amiibo_done = sum(bool(item["termine"]) for item in amiibo_items)
    detected_content = official_map["selected_mode"]
    detected_items = dlc_items if detected_content == "dlc" else base_items
    context = save_context or {}
    save_mode = context.get("mode") or ("expert" if _done(context.get("is_expert")) else "normal")

    def progress(items: list[dict], *, manual: bool) -> dict:
        automatic_done = sum(bool(item["termine"]) for item in items)
        result = {
            "faits_automatiques": automatic_done,
            "total_automatique": len(items),
            "faits_manuels": None if manual else 0,
            "total_manuel": len(manual_required) if manual else 0,
            "total": len(items) + (len(manual_required) if manual else 0),
            "mode": "automatique + suivi manuel local" if manual else "automatique uniquement",
        }
        result["pourcentage_automatique"] = round(100 * automatic_done / len(items), 2) if items else 0
        return result

    profiles = []
    for profile in standard["profiles"]:
        value = dict(profile)
        if profile["id"] == "base":
            value["progress"] = progress(base_items, manual=True)
            value["available"] = save_mode == "normal"
        elif profile["id"] == "dlc":
            value["progress"] = progress(dlc_items, manual=True)
            value["available"] = save_mode == "normal"
        elif profile["id"] == "automatique":
            selected = progress(detected_items, manual=False)
            value["progress"] = {
                "faits": selected["faits_automatiques"], "total": selected["total_automatique"],
                "pourcentage": selected["pourcentage_automatique"], "mode": "automatique uniquement",
            }
            value["selected_content_profile"] = detected_content
            value["available"] = True
        elif profile["id"] == "amiibo":
            value["progress"] = {"faits": amiibo_done, "total": len(amiibo_items), "mode": "optionnel"}
            value["available"] = True
        elif profile["id"] == "carte":
            value["progress"] = {**official_map, "mode": "officiel"}
            value["available"] = True
        elif profile["id"] == "expert":
            if save_mode == "expert":
                value["progress"] = progress(detected_items, manual=True)
                value["progress"]["mode"] = "slot Expert + suivi manuel local"
                value["available"] = True
                value["selected_content_profile"] = detected_content
            else:
                value["progress"] = {"faits": None, "total": None, "mode": "ouvrir un slot 6 ou 7 du mode Expert"}
                value["available"] = False
        profiles.append(value)

    selected_profile = "expert" if save_mode == "expert" else detected_content

    return {
        **standard,
        "categories": resolved,
        "profiles": profiles,
        "global_score": {
            **standard["global_score"],
            "available": required_incomplete == 0,
            "reason": ("Référentiel entièrement implémenté ; chaque profil combine son périmètre automatique avec le suivi manuel local lorsqu'il s'applique."
                       if required_incomplete == 0 else
                       f"{required_incomplete} catégorie(s) obligatoire(s) restent incomplètes."),
            "profile": selected_profile,
        },
        "selection": {
            "save_mode": save_mode,
            "detected_content_profile": detected_content,
            "selected_profile": selected_profile,
            "choices": ["automatique", "base", "dlc", "amiibo", "expert"],
            "detection": context.get("detection", "flag IsLastPlayHardMode" if save_mode == "expert" else "progression de la sauvegarde"),
        },
        "audit": {"categories": len(resolved), "axes": len(standard["axes"]),
                  "par_statut": status_counts, "obligatoires_incompletes": required_incomplete},
    }


def _guide_audit(items: list[dict], map_layers: list[dict]) -> dict:
    guides = [item.get("guide", {}) for item in items + map_layers]
    specificity = {}
    for guide in guides:
        key = guide.get("specificity", "absent")
        specificity[key] = specificity.get(key, 0) + 1
    farm_layers = [item for item in map_layers if item.get("farm")]
    quality_counts = {"niveau_1": 0, "niveau_2": 0, "niveau_3": 0}
    invalid_complete = []
    generic_markers = ("vérifier le dialogue final", "non renseigné", "fiche universelle")
    for item in items + map_layers:
        guide = item.get("guide", {})
        level = guide.get("quality_level")
        if level in {1, 2, 3}:
            quality_counts[f"niveau_{level}"] += 1
        if level == 3:
            text = " ".join(str(value) for value in guide.get("detailed_steps", [])).lower()
            reasons = []
            if len(guide.get("detailed_steps", [])) < 3:
                reasons.append("moins de trois étapes")
            if not guide.get("sources"):
                reasons.append("aucune source")
            if not guide.get("rewards"):
                reasons.append("récompense absente")
            if any(marker in text for marker in generic_markers):
                reasons.append("contenu générique")
            if reasons:
                invalid_complete.append({
                    "tracking_id": item.get("tracking_id"), "raisons": reasons,
                })
    return {
        "schema_version": 2,
        "total": len(guides),
        "version_3": sum(guide.get("version") == 3 for guide in guides),
        "avec_solution_detaillee": sum(bool(guide.get("detailed_steps")) for guide in guides),
        "avec_prerequis": sum(bool(guide.get("prerequisites")) for guide in guides),
        "avec_recompense": sum(bool(guide.get("rewards")) for guide in guides),
        "par_specificite": specificity,
        "par_niveau_qualite": quality_counts,
        "solutions_completes_invalides": invalid_complete,
        "solutions_completes_valides": quality_counts["niveau_3"] - len(invalid_complete),
        "sanctuaires_sans_mecanique": sum(
            item.get("categorie") in {"sanctuaires", "coffres_sanctuaires"}
            and not item.get("guide", {}).get("mechanic") for item in items
        ),
        "korogus_position_exacte_type_non_invente": sum(
            item.get("categorie") == "korogus"
            and item.get("guide", {}).get("specificity") == "exact_location" for item in items
        ),
        "points_farm_avec_avertissement_lune_de_sang": sum(
            any("lune de sang" in warning.lower() for warning in item.get("guide", {}).get("warnings", []))
            for item in farm_layers
        ),
        "points_farm_total": len(farm_layers),
        "sources": [
            "BOTW Object Map pour les coordonnées et les données d'objets",
            "Index de solutions de sanctuaires pour le contrôle des mécanismes",
            "Index des 900 Korogus pour le contrôle de couverture",
        ],
    }


def _nomenclature_audit(items: list[dict], map_layers: list[dict]) -> dict:
    """Contrôle récursivement les textes visibles, y compris l'intérieur des fiches."""
    reference = load_nomenclature_reference()
    visible_keys = {"name", "label", "region", "subtype", "content_origin_label",
                    "action", "completion_condition", "reward", "contenu"}
    forbidden = tuple(reference.get("forbidden_visible_tokens", [])) + (
        "rouge/de base", "bleu/intermédiaire", "blanc/noir", "main_quests",
        "shrine_quests", "side_quests", "pyschologique", "quans s'arrêter",
        "Malanya", "Filet archéonique", "Selle archéonique", "Bouclier Hylien",
        "Hyrule central",
    )
    issues = []

    def inspect_text(tracking_id: str | None, path: str, value: str) -> None:
        for token in forbidden:
            if token.lower() in value.lower():
                issues.append({"tracking_id": tracking_id, "champ": path,
                               "valeur": value, "motif": token})

    skipped_guide_keys = {"sources", "objective_key", "quest_evidence", "category"}

    def walk_guide(tracking_id: str | None, value: object, path: str = "guide") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key not in skipped_guide_keys:
                    walk_guide(tracking_id, child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk_guide(tracking_id, child, f"{path}[{index}]")
        elif isinstance(value, str) and not value.startswith(("http://", "https://")):
            inspect_text(tracking_id, path, value)

    for item in items + map_layers:
        tracking_id = item.get("tracking_id")
        for key in visible_keys:
            value = item.get(key)
            if isinstance(value, str):
                inspect_text(tracking_id, key, value)
        walk_guide(tracking_id, item.get("guide", {}))
    enemy_layers = [item for item in map_layers if item.get("layer_type", "").startswith("enemy_")]
    return {
        "schema_version": 2,
        "locale": "fr-FR",
        "statut": "complet" if not issues else "à corriger",
        "elements_visibles_controles": len(items) + len(map_layers),
        "points_ennemis_controles": len(enemy_layers),
        "sous_types_ennemis": len({item.get("subtype") for item in enemy_layers}),
        "anomalies": issues,
        "reference_schema_version": reference.get("schema_version"),
        "champs_de_fiches_controles_recursivement": True,
        "identifiants_techniques_preserves": True,
        "note": "Les graphies officielles du jeu sont conservées, même lorsqu'elles paraissent inhabituelles.",
    }


def analyze(flags: dict[str, object], inventory: list[dict] | None = None,
            save_context: dict | None = None,
            *, use_precompiled_nomenclature_audit: bool = True) -> dict:
    catalog = _apply_solution_reference(
        _apply_cartography_reference(copy.deepcopy(load_catalog()))
    )
    _enrich_service_names(catalog)
    definitions = (
        ("sanctuaires", "Sanctuaires", "shrines", "flags", False),
        ("coffres_sanctuaires", "Coffres des sanctuaires", "shrine_chests", "shrine_chests", False),
        ("coffres_monde", "Coffres du monde", "world_chests", "flags", False),
        ("coffres_donjons", "Coffres des donjons", "dungeon_chests", "flags", False),
        ("quetes_principales", "Quêtes principales", "main_quests", "flags", False),
        ("quetes_sanctuaires", "Quêtes de sanctuaire", "shrine_quests", "flags", False),
        ("quetes_secondaires", "Quêtes secondaires", "side_quests", "flags", False),
        ("souvenirs", "Souvenirs", "memories", "flags", False),
        ("korogus", "Korogus", "koroks", "flags", False),
        ("tours", "Tours", "towers", "flags", False),
        ("lieux", "Lieux nommés", "locations", "flags", False),
        ("hinox", "Hinox", "hinoxes", "flags", False),
        ("talus", "Lithoroks", "taluses", "flags", False),
        ("moldarquors", "Moldarquors", "moldugas", "flags", False),
        ("compendium", "Compendium d'Hyrule", "compendium", "flags", False),
        ("armures", "Armures améliorables possédées", "armor_owned", "armor", False),
        ("armures_max", "Armures au niveau maximal", "armor_owned", "armor_max", False),
        ("equipements_particuliers", "Équipements particuliers possédés", "special_armor", "inventory", False),
        ("harnachements", "Filets et selles obtenus", "horse_gear", "flags", False),
        ("grandes_fees", "Libération des quatre Grandes Fées", "great_fairies", "flags", False),
        ("malanya", "Marlon", "malanya", "flags", False),
        ("epreuves_epee", "Épreuves de l'épée", "trial_of_the_sword", "flags", False),
        ("medailles_kilton", "Médailles de Kilton", "kilton_medals", "flags", False),
        ("recompenses_uniques", "Récompenses uniques", "unique_rewards", "flags", False),
        ("objets_speciaux", "Objets spéciaux et DLC", "special_items", "flags", False),
        # Ces deux vues détaillent des accomplissements déjà comptés ailleurs.
        ("creatures_divines", "Créatures divines", "divine_beasts", "flags", True),
        ("bosses_scenarises", "Boss scénarisés et DLC", "scripted_bosses", "flags", True),
        ("bonus_expansion", "Coffres bonus de l'Expansion Pass", "expansion_bonus_chests", "flags", True),
        ("ameliorations_prodiges", "Pouvoirs des Prodiges améliorés", "champion_upgrades", "flags", True),
        ("fonctionnalites_dlc", "Fonctionnalités de l'Expansion Pass", "dlc_features", "features", True),
        ("tresors_chiens", "Trésors indiqués par les chiens", "manual_dogs", "manual", True),
    )
    categories = {}
    for key, label, source, mode, score_excluded in definitions:
        source_items = (_manual_dog_treasures(catalog) if source == "manual_dogs"
                        else catalog.get(source, []))
        report = (_evaluate_chests(source_items, flags) if mode == "shrine_chests"
                  else _evaluate_armor(source_items, inventory, mode == "armor_max")
                  if mode in {"armor", "armor_max"}
                  else _evaluate_inventory_items(source_items, inventory, key)
                  if mode == "inventory"
                  else _evaluate_dlc_features(source_items, flags)
                  if mode == "features"
                  else _evaluate_manual(source_items, key)
                  if mode == "manual"
                  else _evaluate(source_items, flags, key))
        report["label"] = label
        report["score_excluded"] = score_excluded
        for item in report["elements"]:
            _apply_filter_metadata(item, key)
            _scope_metadata(item)
            item["guide"] = build_guide(item, key, flags)
        categories[key] = report

    automatic_items = [item for data in categories.values() for item in data["elements"]]
    map_layers = _prepare_map_layers(catalog.get("map_layers", []))
    all_items = automatic_items + map_layers
    for item in all_items:
        item["tracking_id"] = _tracking_id(item)
    official_map = _official_map(catalog, flags)
    standard = load_completion_standard()
    effective_context = dict(save_context or {})
    if "mode" not in effective_context and _done(flags.get("IsLastPlayHardMode")):
        effective_context.update({"mode": "expert", "is_expert": True,
                                  "detection": "flag IsLastPlayHardMode"})
    reference = _completion_reference(
        standard, categories, all_items, official_map,
        categories["tresors_chiens"]["elements"], effective_context,
    )
    automatic_profile = next(profile for profile in reference["profiles"] if profile["id"] == "automatique")
    done = automatic_profile["progress"]["faits"]
    total = automatic_profile["progress"]["total"]
    filter_groups = _filter_groups(all_items)
    save_mode = "expert" if effective_context.get("mode") == "expert" else "normal"
    cartography_audit = _cartography_quality_audit(all_items, catalog.get("cartography_audit", {}))
    return {
        "schema_version": 17,
        "categories": categories,
        "synthese": {
            "faits": done, "total": total,
            "pourcentage": round(100 * done / total, 2) if total else 0,
            "libelle": "Indice de couverture automatique",
            "note": "Indice du compagnon, distinct du pourcentage de carte affiché par le jeu.",
        },
        # Alias conservé pour les scripts qui utilisaient la première archive.
        "synthese_technique": {"faits": done, "total": total,
                               "pourcentage": round(100 * done / total, 2) if total else 0},
        "carte_officielle": official_map,
        "referentiel_100": reference,
        "elements": automatic_items,
        "map_layers": map_layers,
        "audit_guides": _guide_audit(automatic_items, map_layers),
        "audit_solutions": {
            **catalog.get("solution_audit", {}),
            "sources": catalog.get("solution_sources", []),
        },
        "audit_nomenclature": (
            copy.deepcopy(load_runtime_nomenclature_audit())
            if use_precompiled_nomenclature_audit
            else _nomenclature_audit(automatic_items, map_layers)
        ),
        "filter_groups": filter_groups,
        "filter_scope_audit": _filter_scope_audit(all_items, filter_groups, save_mode),
        "audit_dlc": catalog.get("dlc_audit", {}),
        "audit_cartographie": {
            **cartography_audit,
            "sources": catalog.get("cartography_sources", []),
        },
        "suivi_manuel": catalog.get("manual", {}),
        "couverture": {
            "automatique": [label for _key, label, _source, _mode, excluded in definitions if not excluded],
            "vues_sans_double_compte": [label for _key, label, _source, _mode, excluded in definitions if excluded],
            "cartographique_informatif": [group["label"] for group in _filter_groups(map_layers)],
            "manuel": ["Trésors de chiens"],
            "non_mesurable_fiablement": [
                "Tous les coffres du monde (beaucoup n'ont pas de flag permanent)",
                "Tous les ennemis ordinaires (réapparition à la lune de sang)",
                "Objets consommables et armes cassables",
            ],
        },
    }