from __future__ import annotations

import copy
import re
from functools import lru_cache
from importlib.resources import files

from .nomenclature_fr import normalize_catalog


@lru_cache(maxsize=1)
def _strings() -> dict[str, str]:
    import json
    raw = json.loads(files("botw_companion.data").joinpath("localization_fr.json").read_text(encoding="utf-8"))
    return raw["strings"]


def _translate_text(value: str, translations: dict[str, str]) -> str:
    if value in translations:
        return translations[value]
    if value.startswith("Coffre - "):
        content = value.removeprefix("Coffre - ")
        suffix = ""
        match = re.search(r" x\d+$", content)
        if match:
            suffix, content = match.group(0), content[:match.start()]
        return "Coffre - " + translations.get(content, content) + suffix
    # Les libellés cartographiques composés contiennent souvent un nom officiel.
    result = value
    for source in sorted(translations, key=len, reverse=True):
        if len(source) >= 5 and source in result:
            result = result.replace(source, translations[source])
    return result


@lru_cache(maxsize=1)
def _editorial_exact() -> dict[str, str]:
    import json
    raw = json.loads(files("botw_companion.data").joinpath("nomenclature_fr_reference.json").read_text(encoding="utf-8"))
    return raw["exact"]


def localize_editorial_text(value: str) -> str:
    """Traduit une donnée éditoriale externe sans modifier sa source bibliographique."""
    if not value:
        return value
    value = value.replace("{{List|", "").replace("<br/>", "").replace("<br>", "")
    value = re.sub(r"\s*;\s*", " ; ", value).strip(" ;")
    translations = {**_strings(), **_editorial_exact()}
    parts = [part.strip() for part in value.split(" ; ")]
    localized = []
    for part in parts:
        quantity = ""
        match = re.search(r"\s×\d+$", part)
        if match:
            quantity, part = match.group(0), part[:match.start()]
        translated = translations.get(part, part)
        if translated == part and part not in translations.values():
            for source in sorted(translations, key=len, reverse=True):
                if len(source) >= 4 and source in translated:
                    translated = translated.replace(source, translations[source])
        localized.append((translated + quantity).strip())
    return " ; ".join(dict.fromkeys(part for part in localized if part))


def _stage_label(flag: str, internal_id: str, index: int) -> str:
    suffix = flag.removeprefix(internal_id + "_") if internal_id else flag
    exact = {
        "Activated": "Quête activée", "Ready": "Quête disponible",
        "GetShirt": "Tunique du Prodige obtenue", "Find11": "Onze souvenirs retrouvés",
        "Camera": "Appareil photo débloqué", "Carry": "Flamme bleue transportée",
        "Fired": "Fourneau allumé", "Repaired": "Tablette réparée", "Permit": "Accès au laboratoire accordé",
        "Battle": "Combat préparé", "BattlePlaying": "Combat en cours", "BattleSucceeded": "Combat réussi",
        "BattleFinished": "Combat terminé", "BattleEscape": "Combat interrompu",
        "Dungeon": "Créature divine atteinte", "ToRemains": "Retour vers la créature divine",
        "Naked": "Équipement retiré", "Warning": "Épreuve extérieure déclenchée", "OnceRetire": "Épreuve quittée une première fois",
        "Extermination": "Ennemis éliminés", "Exterminate": "Ennemis éliminés", "Beated": "Mini-boss vaincu",
        "Maracus": "Maracas retrouvés", "10kokko": "Dix cocottes retrouvées", "Light": "Flèches enflammées utilisées",
        "GiveUtsuwa": "Réceptacle confié", "HorseGet": "Cheval capturé", "Failed": "Tentative échouée",
        "Again": "Nouvelle tentative", "Answer": "Réponse obtenue", "Report": "Retour auprès du donneur",
        "Meet": "Personnage rencontré", "Explain": "Explications reçues", "Shot": "Photographie prise",
        "Wood": "Bois remis", "Repurchase": "Maison achetée", "Furniture": "Maison entièrement aménagée",
        "Salvage": "Trésor récupéré", "Remove": "Objet responsable retiré", "GetFlower": "Fleur obtenue",
        "PresentFlower": "Fleur offerte", "Give": "Objet demandé remis", "SearchRelief": "Monuments recherchés",
        "Get": "Objet demandé obtenu", "Retire": "Épreuve quittée",
    }
    if suffix in exact:
        return exact[suffix]
    match = re.fullmatch(r"Seek([123])(?:st|nd|rd)Dungeon", suffix)
    if match:
        return f"Sanctuaire de l'épreuve {match.group(1)} recherché"
    match = re.fullmatch(r"(?:Step|Active|Dungeon)(\d+)", suffix)
    if match:
        return f"Progression interne {int(match.group(1))}"
    if suffix.endswith("Clear"):
        return "Objectif intermédiaire validé"
    return f"Progression interne {index}"


def localize_catalog(catalog: dict) -> dict:
    """Retourne une copie localisée, sans toucher aux flags et identifiants internes."""
    data = copy.deepcopy(catalog)
    translations = _strings()
    technical = {
        "id", "flag", "hash", "acteur", "quest_internal_id", "any_flags",
        "usage_flags", "content_origin", "feature",
    }

    def walk(value, key: str | None = None):
        if isinstance(value, dict):
            localized = {k: walk(v, k) for k, v in value.items()}
            if "quest_stage_flags" in localized:
                internal_id = localized.get("quest_internal_id", "")
                for index, stage in enumerate(localized["quest_stage_flags"], 1):
                    stage["label"] = _stage_label(stage.get("flag", ""), internal_id, index)
            return localized
        if isinstance(value, list):
            return [walk(item, key) for item in value]
        if isinstance(value, str) and key not in technical and not key.endswith("_flag"):
            return _translate_text(value, translations)
        return value

    return normalize_catalog(walk(data))