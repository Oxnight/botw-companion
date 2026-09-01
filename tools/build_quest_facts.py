#!/usr/bin/env python3
"""Ajoute aux flux de quête les faits éditoriaux vérifiables de Zelda Wiki."""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path


API = "https://zeldawiki.wiki/w/api.php"
SOURCE = {"name": "Zelda Wiki - fiches de quêtes", "url": "https://zeldawiki.wiki/wiki/Category:Breath_of_the_Wild_Quests"}
SPECIAL_TITLES = {"Diving Is Beauty!": "Diving is Beauty!", "[Xenoblade Chronicles 2]": "Xenoblade Chronicles 2"}


def _clean_wikitext(value: str) -> str:
    value = re.sub(r"<ref\b[^>]*>.*?</ref>|<ref\b[^>]*/>", "", value, flags=re.S)
    value = re.sub(r"<!--.*?-->", "", value, flags=re.S)
    value = re.sub(r"\[\[(?:File|Image):[^]]+]]", "", value, flags=re.I)
    value = re.sub(r"\[\[[^]|]+\|([^]]+)]]", r"\1", value)
    value = re.sub(r"\[\[([^]]+)]]", r"\1", value)
    value = re.sub(r"{{Qty\|([^}|]+).*?}}", r"×\1", value, flags=re.I)
    value = re.sub(r"{{Rupee\|([^}|]+).*?}}", r"\1 rubis", value, flags=re.I)
    value = re.sub(r"{{Icon List\|[^|}]+\|", "", value, flags=re.I)
    value = re.sub(r"{{(?:Term|Term/Store)\|([^|}]+).*?}}", r"\1", value, flags=re.I)
    previous = None
    while previous != value:
        previous = value
        value = re.sub(r"{{[^{}]*}}", "", value)
    value = value.replace("}}", "")
    lines = [re.sub(r"^\s*[*#:;]+\s*", "", line).replace("''", "").strip() for line in value.splitlines()]
    return " ; ".join(dict.fromkeys(line for line in lines if line and line != "???"))


def _field(wikitext: str, name: str) -> str:
    match = re.search(
        rf"^\|{name}\s*=\s*(.*?)(?=^\|[A-Za-z]+\s*=|^}})",
        wikitext,
        flags=re.M | re.S,
    )
    return _clean_wikitext(match.group(1)) if match else ""


def _fetch(titles: list[str]) -> tuple[dict[str, dict], dict[str, str]]:
    pages: dict[str, dict] = {}
    aliases: dict[str, str] = {}
    for offset in range(0, len(titles), 15):
        batch = titles[offset:offset + 15]
        query = urllib.parse.urlencode({
            "action": "query", "format": "json", "formatversion": 2,
            "titles": "|".join(batch), "prop": "revisions", "rvprop": "content",
            "rvslots": "main", "redirects": 1,
        })
        request = urllib.request.Request(API + "?" + query, headers={"User-Agent": "BOTW-Companion factual-reference-builder/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.load(response)
        for entry in data.get("query", {}).get("normalized", []):
            aliases[entry["from"]] = entry["to"]
        for entry in data.get("query", {}).get("redirects", []):
            aliases[entry["from"]] = entry["to"]
        pages.update({page["title"]: page for page in data["query"]["pages"]})
    return pages, aliases


def _resolve(title: str, aliases: dict[str, str]) -> str:
    seen = set()
    while title in aliases and title not in seen:
        seen.add(title)
        title = aliases[title]
    return title


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text())
    quests = [item for group in ("main_quests", "shrine_quests", "side_quests") for item in catalog[group]]
    requested = [SPECIAL_TITLES.get(item["name"], item["name"]) for item in quests]
    pages, aliases = _fetch(requested)
    facts = {}
    for item, requested_title in zip(quests, requested):
        title = _resolve(requested_title, aliases)
        page = pages.get(title, {})
        revisions = page.get("revisions", [])
        if not revisions:
            continue
        wikitext = revisions[0]["slots"]["main"]["content"]
        facts[item["quest_internal_id"]] = {
            "giver": _field(wikitext, "giver"),
            "location": _field(wikitext, "location"),
            "prerequisite": _field(wikitext, "prereq"),
            "reward": _field(wikitext, "reward"),
            "source": {"name": f"Zelda Wiki - {title}", "url": "https://zeldawiki.wiki/wiki/" + urllib.parse.quote(title.replace(" ", "_"))},
        }
    reference = json.loads(args.reference.read_text())
    reference["quest_facts"] = facts
    reference.setdefault("audit", {})["quests_with_editorial_facts"] = len(facts)
    reference.setdefault("audit", {})["quests_with_named_giver"] = sum(bool(item["giver"]) for item in facts.values())
    reference.setdefault("audit", {})["quests_with_named_reward"] = sum(bool(item["reward"]) for item in facts.values())
    if SOURCE not in reference.setdefault("sources", []):
        reference["sources"].append(SOURCE)
    assert len(facts) == len(quests), (len(facts), len(quests))
    args.reference.write_text(json.dumps(reference, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()