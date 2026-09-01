#!/usr/bin/env python3
"""Construit la localisation fr-FR à partir de nomenclatures publiques vérifiables.

Le catalogue conserve ses identifiants techniques anglais (flags, acteurs et IDs),
mais toutes les chaînes présentées à l'utilisateur sont remplacées à l'exécution.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from lxml import html


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "botw_companion" / "data" / "catalog.json"
OUTPUT = ROOT / "botw_companion" / "data" / "localization_fr.json"
UA = "BOTW Companion fr-FR localizer/0.8 (+local build tool)"


FIXED = {
    "Animals": "Animaux",
    "Creatures": "Faune",
    "Monsters": "Monstres",
    "Materials": "Matériaux",
    "Equipment": "Équipement",
    "Treasure": "Trésors",
    "Central": "Centre d'Hyrule",
    "Dueling Peaks": "Ouest de Necluda",
    "Eldin": "Ordinn",
    "Faron": "Firone",
    "Gerudo": "Contrées Gerudos",
    "Great Plateau": "Plateau du Prélude",
    "Hateno": "Est de Necluda",
    "Hebra": "Hébra",
    "Lake": "Lac Hylia",
    "Lanayru": "Lanelle",
    "Ridgeland": "Collines d'Hyrule",
    "Tabantha": "Tabanta",
    "Wasteland": "Landes Sauvages",
    "Woodland": "Grande forêt d'Hyrule",
    "head": "tête",
    "chest": "torse",
    "legs": "jambes",
    "FinalTrial": "Épreuve finale de l'Épée",
    "Trial of the Sword": "Épreuves de l'épée",
    "RemainsElectric": "Vah'Naboris",
    "RemainsFire": "Vah'Rudania",
    "RemainsWater": "Vah'Ruta",
    "RemainsWind": "Vah'Medoh",
    "Ancient Furnace": "Fourneau antique",
    "Bridge of Eldin": "Pont d'Ordinn",
    "Flight Range": "Aire d'exercice au vol",
    "Lookout Tower": "Poste d'observation",
    "Jee Noh Shrine": "Sanctuaire de Jino'Yoh",
    "On the Move": "Entre calme et chaos",
    "Suma Sahma Shrine": "Sanctuaire de Suma'Sama",
    "Suma Sahma's Blessing": "Bénédiction de Suma'Sama",
    "The Skull's Eye": "Dans l'œil du crâne",
    "EX Champion Daruk's Song": "EX La Chanson de Daruk",
    "EX Champion Mipha's Song": "EX La Chanson de Mipha",
    "EX Champion Revali's Song": "EX La Chanson de Revali",
    "EX Champion Urbosa's Song": "EX La Chanson d'Urbosa",
    "Divine Beast Vah Medoh": "Vah'Medoh",
    "Divine Beast Vah Naboris": "Vah'Naboris",
    "Divine Beast Vah Rudania": "Vah'Rudania",
    "Divine Beast Vah Ruta": "Vah'Ruta",
    "Diving Is Beauty!": "L'esthétique du plongeon",
    "What's for Dinner?": "Le repas du soir",
    "Sheik's Mask": "Masque de Sheik",
    "Purple Rupee": "Rubis violet",
    "Gold Rupee": "Rubis doré",
    "Majora's Mask": "Masque de Majora",
    "Mounted Archery Camp": "Camp d'entraînement au tir à l'arc",
    "Warbler's Nest": "Sœurs de pierre",
    "Jeddo Bridge": "Pont de Jeddo",
    "Sand-Seal Rally": "Course de morses",
    "Serenne Stable": "Relais de Delass",
    "Sacred Ground Ruins": "Ruines de l'ancien temple",
    "Princess Zelda's Room": "Appartement de Zelda",
    "Princess Zelda's Study": "Salle d'étude de Zelda",
    "Military Training Camp": "Camp d'entraînement militaire",
    "Malanya Spring": "Fontaine de Marlon",
    "Selmie's Spot": "Chalet de Selmie",
    "Pondo's Lodge": "Chalet de Pondo",
    "Tanagar Canyon Course": "Course du canyon de Tanagar",
    "Footrace Check-In": "Accueil de la course à pied",
    "Maw of Death Mountain": "Gueule de la montagne de la Mort",
    "Moat Bridge": "Pont des douves",
    "Manhala Bridge": "Pont de Manhala",
    "Moor Garrison Ruins": "Ruines de la garnison de Moor",
    "UMiiVillageShopBougu": "Boutique d'armures d'Euzero",
    "UMiiVillageShopJewel": "Bijouterie d'Euzero",
    "UMiiVillageShopYadoya": "Auberge d'Euzero",
    "UMiiVillageShopYorozu": "Bazar d'Euzero",
    "Akkala Ancient Tech Lab": "Laboratoire antique d'Akkala",
    "Hateno Ancient Tech Lab": "Laboratoire antique d'Elimith",
    "Shrine of Resurrection": "Sanctuaire de la Renaissance",
}

# Noms de personnages de la version française européenne. Ces graphies sont
# contrôlées contre les tables de nomenclature Zelda Wiki et les guides français
# du Palais de Zelda ; les identifiants internes anglais restent inchangés.
CHARACTER_NAMES = {
    "Amali": "Camailla", "Bayge": "Bagodet", "Bedoli": "Della",
    "Benja": "Benjamin", "Bladon": "Landonn", "Bolson": "Sérasieh",
    "Bozai": "Tuska", "Cado": "Vocah", "Calip": "Caly",
    "Chio": "Papistus", "Cima": "Shimina", "Clavia": "Clévia",
    "Cottla": "Pricota", "Dalia": "Tiklama", "Domidak": "Domida",
    "Dugby": "Plèle", "Finley": "Alfine", "Fronk": "Nelsice",
    "Fugo": "Fuhgo", "Garini": "Argose", "Geggle": "Kasah",
    "Gesane": "Ghipa", "Gotter": "Gottah", "Greta": "Egrouss",
    "Guy": "Migaro", "Hagie": "Deza", "Hestu": "Noïa",
    "Hudson": "Grosaillieh", "Isha": "Azasha", "Izra": "Elos",
    "Jana": "Jun", "Jerrin": "Jérine", "Jiahto": "Jitato",
    "Jogo": "Johgo", "Juannelle": "Fruguette", "Juney": "Junoh",
    "Kass": "Asarim", "Kheel": "Quill", "Kiana": "Plati",
    "Kima": "Mark", "Koko": "Coconoa", "Koyin": "Naye",
    "Kula": "Almus", "Laflat": "Mébol", "Laine": "Lamenn",
    "Laruta": "Narutel", "Lasli": "Amboise", "Ledo": "Telago",
    "Lester": "Pistou", "Liana": "Lobinn", "Loone": "Lune",
    "Malena": "Merveila", "Manny": "Hamel", "Mayro": "Mero",
    "Medda": "Filip", "Molli": "Mohino", "Nebb": "Erhêt",
    "Nobiro": "Allium", "Nobo": "Lasto", "Parcy": "Parisse",
    "Paya": "Pahya", "Peeks": "Pecanis", "Perosa": "Surosse",
    "Pikango": "Kangis", "Pokki": "Pohrpi", "Purah": "Pru'ha",
    "Ramella": "Labira", "Rensa": "Nagache", "Rola": "Cherrola",
    "Rotana": "Rhodoni", "Ruli": "Lespe", "Sebasto": "Bacchyas",
    "Sesami": "Cézam", "Straia": "Staille", "Symin": "Canel",
    "Tali": "Pihmène", "Tasho": "Coquis", "Toffa": "Tabos",
    "Toren": "Tholu", "Torfeau": "Poréa", "Tumbo": "Pemto",
    "Wabbin": "Kamis", "Walton": "Cernus", "Zooki": "Glanis",
    "Zyle": "Zucchi",
}


def get_json(url: str) -> dict:
    return json.loads(urlopen(Request(url, headers={"User-Agent": UA}), timeout=60).read())


def nomenclature(names: list[str]) -> dict[str, str]:
    """Récupère le nom français européen, de préférence celui marqué BotW."""
    result: dict[str, str] = {}
    endpoint = "https://zeldawiki.wiki/w/api.php"
    for start in range(0, len(names), 20):
        batch = names[start:start + 20]
        source = "\n".join(
            f"@@B{i}@@{{{{Nomenclature|{name}}}}}@@E{i}@@"
            for i, name in enumerate(batch)
        )
        payload = urlencode({
            "action": "expandtemplates", "text": source,
            "prop": "wikitext", "format": "json",
        }).encode()
        request = Request(endpoint, data=payload, headers={"User-Agent": UA})
        expanded = json.loads(urlopen(request, timeout=120).read())["expandtemplates"]["wikitext"]
        for i, name in enumerate(batch):
            try:
                segment = expanded.split(f"@@B{i}@@", 1)[1].split(f"@@E{i}@@", 1)[0]
            except IndexError:
                continue
            candidates = []
            for match in re.finditer(r'<span lang="fr-FR">(.*?)</span>', segment, re.S):
                raw = match.group(1)
                raw = re.sub(r"\[\[:fr:[^|\]]+\|([^\]]+)\]\]", r"\1", raw)
                raw = re.sub(r"\[\[fr:([^\]]+)\]\]", r"\1", raw)
                raw = re.sub(r"<[^>]+>", "", raw)
                value = raw.replace("&nbsp;", " ").replace("&#039;", "'").strip()
                tail = segment[match.end():match.end() + 900]
                candidates.append(("BotW" in tail, value))
            chosen = next((value for botw, value in candidates if botw and value), None)
            chosen = chosen or next((value for _botw, value in candidates if value), None)
            if chosen and chosen.casefold() != name.casefold():
                result[name] = chosen
        time.sleep(0.08)
    return result


def palais_compendium() -> dict[int, str]:
    raw = urlopen("https://www.palaiszelda.com/breathofthewild/encyclopedie.php", timeout=60).read()
    tree = html.fromstring(raw.decode("utf-8"))
    result = {}
    for row in tree.xpath("//table//tr"):
        cells = [" ".join(c.text_content().split()) for c in row.xpath("./th|./td")]
        if len(cells) >= 2 and cells[0].isdigit():
            result[int(cells[0])] = cells[1]
    if len(result) != 385:
        raise RuntimeError(f"Encyclopédie incomplète : {len(result)}/385")
    return result


def palais_map() -> dict:
    return get_json("https://www.palaiszelda.com/breathofthewild/supermap/elements.json")


def nearest(points: list[dict], source: dict, *, strict: bool = True) -> dict:
    pool = list(source.values())
    result = {}
    for item in points:
        px, py = (item["x"] + 5000) * 0.64, (item["z"] + 5000) * 0.64
        match = min(pool, key=lambda p: (float(p["pos_x"]) - px) ** 2 + (float(p["pos_y"]) - py) ** 2)
        distance = ((float(match["pos_x"]) - px) ** 2 + (float(match["pos_y"]) - py) ** 2) ** .5
        if distance > 85 and strict:
            raise RuntimeError(f"Correspondance géographique douteuse : {item['name']} ({distance:.1f}px)")
        if distance <= 85:
            result[item["name"]] = match
    return result


def palais_shrine_trials() -> dict[str, str]:
    """Retourne le titre français de chaque épreuve, indexé par nom du guide."""
    index_url = "https://www.palaiszelda.com/breathofthewild/sanctuaires.php"
    tree = html.fromstring(urlopen(index_url, timeout=60).read().decode("utf-8"))
    pages = sorted({a.get("href").split("#", 1)[0] for a in tree.xpath("//table//a[@href]")})
    result = {}
    for page in pages:
        url = "https://www.palaiszelda.com/breathofthewild/" + page
        detail = html.fromstring(urlopen(url, timeout=60).read().decode("utf-8"))
        for node in detail.xpath("//*[contains(concat(' ', normalize-space(@class), ' '), ' gras ')]"):
            text = " ".join(node.text_content().split())
            if " - " in text:
                name, trial = text.split(" - ", 1)
                if name and trial:
                    result[name.strip()] = trial.strip()
    return result


def base_chest_name(value: str) -> str:
    return re.sub(r" x\d+$", "", value)


def main() -> None:
    catalog = json.loads(CATALOG.read_text())
    strings = dict(FIXED)
    strings.update(CHARACTER_NAMES)

    # Noms affichables pour lesquels Zelda Wiki expose la nomenclature fr-FR.
    query = set()
    for key in ("locations", "shrines", "main_quests", "shrine_quests", "side_quests", "memories", "armor_owned"):
        for item in catalog[key]:
            query.add(item["name"])
            if item.get("nearby"):
                query.add(item["nearby"])
            if item.get("sanctuaire"):
                query.add(item["sanctuaire"])
    for key in ("world_chests", "dungeon_chests"):
        query.update(base_chest_name(item["contenu"]) for item in catalog[key])
    for group in catalog.get("manual", {}).values():
        for item in group:
            query.update(str(item[field]) for field in ("location", "item") if item.get(field))
    strings.update(nomenclature(sorted(query)))

    # Encyclopédie : numérotation identique au jeu, donc correspondance sans ambiguïté.
    compendium = palais_compendium()
    for item in catalog["compendium"]:
        if item.get("number") in compendium:
            strings[item["name"]] = compendium[item["number"]]
    strings.update({
        "Sky Octorok": "Octo volant", "Golden Bokoblin": "Bokoblin doré",
        "Golden Moblin": "Moblin doré", "Golden Lizalfos": "Lézalfos doré",
        "Golden Lynel": "Lynel doré", "Monk Maz Koshia": "Guide Miz'Kyosia",
        "Igneo Talus Titan": "Méga Magrok", "Molduking": "Arquor Rex",
        "One-Hit Obliterator": "Destructeur",
    })

    # Sanctuaires, épreuves et tours : rapprochement direct par coordonnées.
    map_data = palais_map()
    base = [x for x in catalog["shrines"] if not x["dlc"]]
    dlc = [x for x in catalog["shrines"] if x["dlc"]]
    shrine_matches = nearest(base, map_data["sanctuaire"], strict=False)
    shrine_matches.update(nearest(dlc, map_data["sanctuaireDLC"], strict=False))
    shrine_trials = palais_shrine_trials()
    for english, match in shrine_matches.items():
        strings[english] = match["nom"]
        source = next(x for x in catalog["shrines"] if x["name"] == english)
        if source.get("trial"):
            strings[source["trial"]] = match["titre"]
    for source in catalog["shrines"]:
        french = strings.get(source["name"], "").removeprefix("Sanctuaire de ")
        if source.get("trial") and french in shrine_trials:
            strings[source["trial"]] = shrine_trials[french]
    for english, match in nearest(catalog["towers"], map_data["tour"]).items():
        strings[english] = match["nom"]

    # Noms génériques des miniboss suivis par leur index stable.
    for i in range(1, 41):
        strings[f"Talus {i:02d}"] = f"Lithorok {i:02d}"
    for i in range(1, 5):
        strings[f"Molduga {i:02d}"] = f"Moldarquor {i:02d}"

    # Les appellations d'ensembles ne sont pas toutes des pages autonomes.
    strings.update({
        "Ancient": "archéonique", "Barbarian": "barbare", "Climber": "d'escalade",
        "Desert Voe": "des sablons", "Fierce Deity": "du dieu démon",
        "Flamebreaker": "de pierre", "Hero": "du héros", "Hylian": "hylien",
        "Radiant": "nox", "Rubber": "isolant", "Sky": "du ciel",
        "Snowquill": "piaf", "Soldier": "de soldat", "Stealth": "furtif",
        "Time": "du temps", "Twilight": "du Crépuscule", "Wild": "des landes",
        "Wind": "du vent", "Zora": "zora",
    })

    payload = {
        "schema_version": 1,
        "locale": "fr-FR",
        "sources": [
            "Palais de Zelda - encyclopédie, sanctuaires et carte interactive",
            "Zelda Wiki - tables de nomenclature française européenne",
        ],
        "strings": dict(sorted(strings.items())),
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(strings)} traductions écrites dans {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()