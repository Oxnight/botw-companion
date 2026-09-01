#!/usr/bin/env python3
"""Lie les états internes du journal aux quêtes du catalogue."""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
import re
import unicodedata


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", value)


def humanize(suffix: str) -> str:
    replacements = {
        "1st": "premier", "2nd": "deuxième", "3rd": "troisième", "4th": "quatrième",
        "Seek": "Chercher ", "Dungeon": "sanctuaire", "Remains": "créature divine",
        "Step": "Étape ", "Get": "Obtenir ", "Find": "Trouver ", "Talk": "Parler ",
        "Open": "Ouvrir ", "Complete": "Terminer ", "Failed": "Échec ",
        "Again": "Nouvelle tentative", "Horse": "Cheval ", "Photo": "Photo ",
    }
    text = suffix
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"[_-]+", " ", text)
    text = re.sub(r"(?<=[a-zà-ÿ])(?=[A-Z])", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1].upper() + text[1:] if text else "Étape interne"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--questmsg", type=Path, required=True)
    parser.add_argument("--hashes", type=Path, required=True)
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text())
    flag_names = {
        line.split(";", 2)[2]
        for line in args.hashes.read_text().splitlines()
        if line.count(";") >= 2
    }
    quest_data = {}
    for path in args.questmsg.glob("QL_*.xmsbt"):
        text = path.read_text()
        title_match = re.search(r'<entry label="[^"]+_Name">\s*<text>(.*?)</text>', text, re.S)
        if not title_match:
            continue
        title = html.unescape(re.sub(r"<.*?>", "", title_match.group(1))).strip()
        internal = path.stem.removeprefix("QL_")
        flags = []
        for label in re.findall(r'<entry label="QL_([^"]+)">', text):
            if label not in flag_names:
                continue
            suffix = label.removeprefix(internal + "_")
            if suffix in {"Name", "Desc", "Finish", "Finished", "Activated", "Ready"}:
                continue
            flags.append({"flag": label, "label": humanize(suffix)})
        quest_data[norm(title)] = {"internal": internal, "stages": flags}

    counts = {"quests": 0, "started": 0, "stages": 0}
    for group in ("main_quests", "shrine_quests", "side_quests"):
        for quest in catalog[group]:
            data = quest_data.get(norm(quest["name"]))
            if not data:
                raise RuntimeError(f"QuestMsg introuvable : {quest['name']}")
            counts["quests"] += 1
            activated = f"{data['internal']}_Activated"
            ready = f"{data['internal']}_Ready"
            start_flag = activated if activated in flag_names else ready
            if start_flag not in flag_names:
                raise RuntimeError(f"Flag de découverte introuvable : {quest['name']}")
            quest["started_rule"] = [{"flag": start_flag, "value": True}]
            quest["quest_internal_id"] = data["internal"]
            quest["quest_stage_flags"] = data["stages"]
            counts["started"] += 1
            counts["stages"] += len(data["stages"])

    catalog["schema_version"] = 5
    args.catalog.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    print(f"{counts['started']}/{counts['quests']} flags de découverte ; {counts['stages']} états intermédiaires")


if __name__ == "__main__":
    main()