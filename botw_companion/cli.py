from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

from .analyzer import analyze
from .blood_moon import blood_moon_status
from .save import SaveError, identify_platform, load_save, parse_inventory
from .server import serve
from .synchronization import ReliableSaveSync


def _item_line(item: dict) -> str:
    name = item.get("name", item.get("id", "élément"))
    if item.get("categorie") in {"armures", "armures_max"}:
        state = item.get("etoiles", "☆☆☆☆") if item.get("possede") else "non possédée"
        line = f"- {name} - {state}"
        upgrade = item.get("prochaine_amelioration")
        if upgrade:
            needs = ", ".join(
                f"{material['name']} {material['possede']}/{material['requis']}"
                for material in upgrade["materiaux"]
            )
            line += f" → niveau {upgrade['niveau_cible']} ({needs})"
        return line
    if "x" in item and "z" in item:
        roles = {"depart": "départ", "objectif": "objectif", "souvenir": "souvenir"}
        role = roles.get(item.get("location_role"))
        prefix = f"{role} : " if role else ""
        nearby = f" - près de {item['nearby']}" if item.get("nearby") else ""
        extra = len(item.get("geo_points", [])) - 1
        suffix = f" - {extra} autre(s) point(s) détaillé(s)" if extra > 0 else ""
        return f"- {name} - {prefix}X {item['x']:.1f}, Z {item['z']:.1f}{nearby}{suffix}"
    return f"- {name}"


def _save_context(slot_path: Path, flags: dict[str, object]) -> dict:
    slot_number = int(slot_path.name) if slot_path.name.isdigit() else None
    flag_is_expert = bool(flags.get("IsLastPlayHardMode"))
    if slot_number in range(8):
        is_expert = slot_number in {6, 7}
        detection = (f"slot {slot_number} réservé au mode Expert" if is_expert else
                     f"slot {slot_number} réservé au mode normal")
    else:
        is_expert = flag_is_expert
        detection = ("flag IsLastPlayHardMode (numéro de slot indisponible)" if flag_is_expert else
                     "numéro de slot et indicateur Expert indisponibles")
    return {
        "mode": "expert" if is_expert else "normal",
        "is_expert": is_expert,
        "slot_number": slot_number,
        "detection": detection,
    }


def _payload(path: str | None) -> dict:
    slot, caption, flags = load_save(path)
    inventory = parse_inventory(slot.path / "game_data.sav")
    context = _save_context(slot.path, flags)
    report = analyze(flags, inventory, context)
    report["lune_de_sang"] = blood_moon_status(flags)
    report["sauvegarde"] = {
        "slot": slot.path.name,
        "chemin": str(slot.path),
        "date": slot.date.isoformat(sep=" ", timespec="seconds"),
        "plateforme": identify_platform(slot.path / "game_data.sav"),
        "rubis": caption.get("CurrentRupee"),
        "temps_jeu_secondes": caption.get("PlayReport_PlayTime"),
        "mode": context["mode"],
        "detection_mode": context["detection"],
    }
    return report


def _map_for_mode(payload: dict, mode: str) -> dict:
    official = payload["carte_officielle"]
    selected = official["selected_mode"] if mode == "automatique" else mode
    return {**official, **official.get("scenarios", {}).get(selected, {}), "selected_mode": selected}


def _profile_for_mode(payload: dict, mode: str) -> dict:
    profiles = {item["id"]: item for item in payload["referentiel_100"]["profiles"]}
    return profiles[mode]


def _print_summary(payload: dict, map_mode: str = "automatique",
                   profile_mode: str = "automatique") -> None:
    save = payload["sauvegarde"]
    print(f"Dernière sauvegarde : slot {save['slot']} - {save['date']}")
    print(f"Plateforme : {save['plateforme']}")
    print(f"Chemin : {save['chemin']}")
    for name, data in payload["categories"].items():
        print(f"{data.get('label', name.replace('_', ' ').title()):32} {data['faits']:>4} / {data['total']:<4}  reste {data['total'] - data['faits']}")
    official = _map_for_mode(payload, map_mode)
    visibility = (
        "visible dans le jeu"
        if official["visible_dans_le_jeu"]
        else "prévision - compteur encore masqué dans le jeu jusqu'à la première victoire contre Ganon"
    )
    print(
        f"\nCarte officielle BOTW : {official['faits']} / {official['total']} "
        f"({official['pourcentage']:.2f} %) - {visibility}"
    )
    selection = "automatique" if map_mode == "automatique" else "forcée"
    print(f"Formule : {'jeu + DLC' if official['selected_mode'] == 'dlc' else 'jeu de base'} ({selection}) ; chaque marqueur a le même poids.")
    profile = _profile_for_mode(payload, profile_mode)
    progress = profile["progress"]
    if profile.get("available") is False:
        print(f"\nProfil {profile['label']} : indisponible - {progress['mode']}.")
    elif progress.get("faits") is not None:
        percent = 100 * progress["faits"] / progress["total"] if progress["total"] else 0
        print(f"\nProfil {profile['label']} : {progress['faits']} / {progress['total']} ({percent:.2f} %)")
    else:
        print(f"\nProfil {profile['label']} : {progress['faits_automatiques']} / {progress['total_automatique']} automatiques ; "
              f"0 / {progress['total_manuel']} manuel dans la CLI ; dénominateur complet {progress['total']}.")
    reference = payload.get("referentiel_100")
    if reference:
        audit = reference["audit"]
        print(
            f"Référentiel 100 % : {audit['categories']} catégories dans {audit['axes']} axes ; "
            f"{audit['obligatoires_incompletes']} catégories obligatoires restent à implémenter."
        )
        print(reference["global_score"]["reason"])


def _watch(path: str | None, interval: float, map_mode: str = "automatique",
           profile_mode: str = "automatique") -> None:
    sync = ReliableSaveSync(path, lambda: _payload(path))
    previous_revision = 0
    print("Surveillance active; Ctrl+C pour arrêter.")
    while True:
        result = sync.check(include_report=True)
        payload = result["report"]
        revision = result["synchronisation"]["report_revision"]
        if payload is not None and revision != previous_revision:
            if previous_revision:
                print("\nNouvelle sauvegarde détectée.")
            _print_summary(payload, map_mode, profile_mode)
            previous_revision = revision
        time.sleep(interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compagnon local de complétion Zelda BOTW pour Switch/Ryujinx")
    sub = parser.add_subparsers(dest="commande", required=True)
    analyse = sub.add_parser("analyse", help="analyser la sauvegarde la plus récente")
    analyse.add_argument("sauvegarde", nargs="?", help="dossier exporté par Ryujinx; auto-détecté si omis")
    analyse.add_argument("--json", action="store_true", dest="as_json")
    analyse.add_argument("--formule-carte", choices=("automatique", "base", "dlc"), default="automatique")
    analyse.add_argument("--profil", choices=("automatique", "base", "dlc", "amiibo", "expert"), default="automatique")
    reste = sub.add_parser("reste", help="lister les éléments restants")
    reste.add_argument("sauvegarde", nargs="?", help="dossier exporté par Ryujinx; auto-détecté si omis")
    reste.add_argument("--categorie", required=True)
    reste.add_argument("--json", action="store_true", dest="as_json")
    watch = sub.add_parser("surveille", help="réanalyser à chaque nouvelle sauvegarde")
    watch.add_argument("sauvegarde", nargs="?", help="dossier exporté par Ryujinx; auto-détecté si omis")
    watch.add_argument("--intervalle", type=float, default=3.0)
    watch.add_argument("--formule-carte", choices=("automatique", "base", "dlc"), default="automatique")
    watch.add_argument("--profil", choices=("automatique", "base", "dlc", "amiibo", "expert"), default="automatique")
    interface = sub.add_parser("interface", help="ouvrir le tableau de bord local dans le navigateur")
    interface.add_argument("sauvegarde", nargs="?", help="dossier exporté par Ryujinx; auto-détecté si omis")
    interface.add_argument("--port", type=int, default=8765)
    interface.add_argument("--sans-navigateur", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.commande == "surveille":
            _watch(args.sauvegarde, max(args.intervalle, 0.5), args.formule_carte, args.profil)
            return 0
        if args.commande == "interface":
            factory = lambda: _payload(args.sauvegarde)
            sync = ReliableSaveSync(args.sauvegarde, factory)
            serve(factory, port=args.port, open_browser=not args.sans_navigateur,
                  sync_controller=sync)
            return 0
        payload = _payload(args.sauvegarde)
        if args.commande == "analyse":
            print(json.dumps(payload, ensure_ascii=False, indent=2) if args.as_json else "", end="")
            if not args.as_json:
                _print_summary(payload, args.formule_carte, args.profil)
            return 0
        category = args.categorie.lower().replace(" ", "_")
        data = payload["categories"].get(category)
        if data is None:
            choices = ", ".join(payload["categories"])
            raise SaveError(f"Catégorie inconnue. Choix : {choices}")
        if args.as_json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(f"{len(data['restants'])} élément(s) restant(s) dans {category} :")
            for item in data["restants"]:
                print(_item_line(item))
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, SaveError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2