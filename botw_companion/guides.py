"""Fiches d'accompagnement individuelles et honnêtes pour chaque objectif."""
from __future__ import annotations

from collections.abc import Callable

from .guide_enrichment import enrich_guide


def _step(title: str, instruction: str, state: str = "a_faire", **extra: object) -> dict:
    return {"title": title, "instruction": instruction, "state": state, **extra}


def _state(done: bool, current: bool = False) -> str:
    return "termine" if done else ("actuel" if current else "a_faire")


def _position(item: dict) -> str:
    if item.get("x") is None or item.get("z") is None:
        return "Aucune coordonnée fiable n'est disponible pour cet objectif."
    nearby = f", près de {item['nearby']}" if item.get("nearby") else ""
    return f"Rejoins X {item['x']:.1f}, Z {item['z']:.1f}{nearby}."


def _base(item: dict, category: str, summary: str, action: str, condition: str,
          steps: list[dict], *, tips: list[str] | None = None,
          warnings: list[str] | None = None) -> dict:
    sources = []
    seen = set()
    for point in item.get("geo_points", []):
        source = point.get("source")
        url = point.get("source_url")
        key = (source, url)
        if source and key not in seen:
            sources.append({"name": source, "url": url})
            seen.add(key)
    current_step = next((step for step in steps if step.get("state") == "actuel"), None)
    if current_step is None:
        current_step = next((step for step in steps if step.get("state") in {"a_verifier", "a_faire"}), None)
    personalized_action = action
    if current_step is not None:
        personalized_action = f"{current_step['title']} - {current_step['instruction']}"
    return {
        "version": 1,
        "personalized": True,
        "category": category,
        "title": f"Accompagnement - {item.get('name', item.get('id', 'objectif'))}",
        "summary": summary,
        "current_action": "Aucune action : cet objectif est terminé." if item.get("termine") else personalized_action,
        "completion": {
            "condition": condition,
            "detection": item.get("detection", "flag persistant de la sauvegarde"),
            "automatic": True,
        },
        "steps": steps,
        "tips": tips or [],
        "warnings": warnings or [],
        "sources": sources,
    }


def _quest(item: dict, category: str, flags: dict[str, object]) -> dict:
    done, started = item.get("termine", False), item.get("commence", False)
    points = item.get("geo_points", [])
    steps = []
    if points:
        first = points[0]
        start_instruction = (
            f"Va à X {first['x']:.1f}, Z {first['z']:.1f}"
            + (f", près de {first['nearby']}" if first.get("nearby") else "")
            + " puis parle au personnage présent ou déclenche l'événement indiqué par le journal."
        )
        if item.get("name") == "[Xenoblade Chronicles 2]":
            start_instruction = "La quête est commandée automatiquement. Commence par le premier indice géographique ci-dessous."
        steps.append(_step("Découvrir ou activer la quête", start_instruction,
                           _state(done or started, not started and not done), geo_point_index=0))
        active_stages = [stage["label"] for stage in item.get("quest_stage_flags", [])
                         if flags.get(stage["flag"]) is True]
        if active_stages and not done:
            steps.append(_step(
                "Progression interne détectée",
                "Le journal a enregistré : " + ", ".join(active_stages) + ".",
                "actuel",
            ))
        for index, point in enumerate(points[1:], 1):
            if done:
                point_state = "termine"
            elif started:
                point_state = "a_verifier"
            else:
                point_state = "verrouille"
            steps.append(_step(
                point["label"],
                f"Rejoins X {point['x']:.1f}, Z {point['z']:.1f}"
                + (f", près de {point['nearby']}" if point.get("nearby") else "") + ".",
                point_state, geo_point_index=index,
            ))
    walkthrough = item.get("quest_walkthrough", {})
    route = walkthrough.get("steps", [])
    if route:
        if started and not done:
            steps.append(_step(
                "Reprendre la solution détaillée",
                "Compare le journal du jeu aux actions ci-dessous et reprends à la première action qui n'est pas encore validée.",
                "actuel",
            ))
        for index, instruction in enumerate(route, 1):
            if done:
                route_state = "termine"
            elif not started and index == 1:
                route_state = "actuel"
            elif started:
                route_state = "a_verifier"
            else:
                route_state = "verrouille"
            steps.append(_step(f"Solution {index}/{len(route)}", instruction, route_state))
    steps.append(_step(
        "Valider la quête dans le journal",
        "Termine la dernière consigne, attends la mise à jour du journal puis effectue une sauvegarde.",
        _state(done, started and not done),
    ))
    kind = {
        "quetes_principales": "quête principale",
        "quetes_sanctuaires": "quête de sanctuaire",
        "quetes_secondaires": "quête secondaire",
    }[category]
    status = "terminée" if done else ("déjà découverte" if started else "pas encore découverte")
    warnings = []
    if started and not done:
        warnings.append("Certains marqueurs intermédiaires ne prouvent pas séparément chaque action : le journal du jeu reste la référence pour choisir où reprendre.")
    if category == "quetes_sanctuaires":
        warnings.append("Le départ de la quête et le sanctuaire obtenu sont deux points distincts dans cette fiche.")
    return _base(
        item, category,
        f"Cette {kind} est {status}. La fiche suit son départ, ses points connus et sa validation officielle.",
        "Commence par l'étape marquée comme actuelle, puis sauvegarde après la mise à jour du journal.",
        "Le flag officiel de fin du journal doit être enregistré dans la sauvegarde.",
        steps,
        tips=["Utilise les boutons Carte de la fiche pour afficher chaque étape sans ressaisir les coordonnées."],
        warnings=warnings,
    )


def _shrine(item: dict, category: str, flags: dict[str, object]) -> dict:
    done = item.get("termine", False)
    shrine_id = item.get("id")
    entered = bool(shrine_id and flags.get(f"Enter_{shrine_id}")) or done
    opened = bool(shrine_id and flags.get(f"Open_{shrine_id}")) or entered
    chest = bool(shrine_id and flags.get(f"CompleteTreasure_{shrine_id}"))
    steps = [
        _step("Atteindre le sanctuaire", _position(item), _state(done or opened, not opened)),
        _step("Activer le terminal", "Examine le terminal extérieur pour ouvrir l'entrée et le point de téléportation.",
              _state(done or opened, not opened)),
        _step(f"Réussir l'épreuve - {item.get('trial') or 'épreuve du sanctuaire'}",
              "Résous l'épreuve intérieure et rejoins l'autel.", _state(done, opened and not done)),
        _step("Récupérer le coffre facultatif", "Explore les salles annexes avant de quitter le sanctuaire.",
              _state(chest, opened and not chest)),
        _step("Examiner l'autel", "Parle au moine et récupère l'emblème de triomphe.", _state(done)),
    ]
    if category == "coffres_sanctuaires":
        steps = [
            _step("Retourner dans le sanctuaire", _position(item), _state(done, not done)),
            _step("Trouver et ouvrir le coffre", "Inspecte le parcours et les salles secondaires avant l'autel.", _state(done, not done)),
            _step("Sauvegarder", "Attends l'enregistrement du symbole de coffre à côté du sanctuaire.", _state(done)),
        ]
        return _base(item, category, f"Coffre facultatif de {item.get('trial') or shrine_id or item.get('name', 'ce sanctuaire')}.",
                     "Retourne dans le sanctuaire et cherche le coffre manquant.",
                     "Le flag global de coffre du sanctuaire doit devenir vrai.", steps,
                     warnings=[item.get("raison", "Le coffre n'est pas encore validé.")])
    return _base(item, category,
                 f"Sanctuaire de la région {item.get('region') or 'inconnue'} : {item.get('trial') or 'épreuve non renseignée'}.",
                 "Rejoins le sanctuaire puis poursuis à partir de la première étape inachevée.",
                 "L'autel doit être examiné et le flag Clear du sanctuaire enregistré.", steps,
                 tips=[f"Quête d'accès : {item['quest']}" if item.get("quest") else "Ce sanctuaire ne dépend pas d'une quête répertoriée."],
                 warnings=["Le coffre facultatif possède une validation séparée de celle du sanctuaire."])


def _chest(item: dict, category: str) -> dict:
    done = item.get("termine", False)
    content = item.get("contenu") or "contenu non identifié"
    sector = item.get("secteur") or item.get("section") or "secteur non précisé"
    position = _position(item) if item.get("x") is not None else f"Explore {sector}."
    steps = [
        _step("Rejoindre le coffre", position, _state(done, not done)),
        _step("Ouvrir le coffre", f"Ouvre ce coffre contenant : {content}.", _state(done, not done)),
        _step("Enregistrer l'ouverture", "Effectue une sauvegarde après l'ouverture.", _state(done)),
    ]
    return _base(item, category, f"Coffre persistant de {sector}. Contenu : {content}.",
                 "Rejoins sa position et ouvre-le.",
                 "Le flag persistant propre à ce coffre doit être présent.", steps,
                 warnings=["Seuls les coffres possédant un flag permanent peuvent être prouvés automatiquement."])


def _memory(item: dict, category: str) -> dict:
    done = item.get("termine", False)
    steps = [
        _step("Rejoindre le lieu du souvenir", _position(item), _state(done, not done), geo_point_index=0),
        _step("Examiner la lueur", "Place-toi dans la zone lumineuse et lance l'examen.", _state(done, not done)),
        _step("Regarder la cinématique", "Laisse la scène se terminer afin qu'elle soit inscrite dans les souvenirs.", _state(done)),
    ]
    return _base(item, category, f"Souvenir {'DLC' if item.get('dlc') else 'du jeu de base'} localisé près de {item.get('nearby', 'ce point')}.",
                 "Rejoins le point exact et déclenche la cinématique.",
                 "Le flag de lecture de la cinématique doit être enregistré.", steps)


def _korok(item: dict, category: str) -> dict:
    done = item.get("termine", False)
    detail = item.get("korok_solution", {})
    label = detail.get("puzzle_label", "Énigme Korogu")
    geo = item.get("geo_points", [])
    first_index = 0 if geo else None
    last_index = len(geo) - 1 if len(geo) > 1 else None
    steps = [
        _step("Rejoindre le puzzle", _position(item), _state(done, not done),
              **({"geo_point_index": first_index} if first_index is not None else {})),
        _step(f"Résoudre : {label}", detail.get("steps", ["Résous l'énigme indiquée."])[1],
              _state(done)),
    ]
    if last_index is not None:
        steps.append(_step("Atteindre la fin du parcours",
                           "Suis dans l'ordre les repères cartographiques vérifiés jusqu'au dernier point.", _state(done),
                           geo_point_index=last_index))
    steps.append(_step("Récupérer la noix", detail.get("steps", ["", "", "Parle au Korogu."])[-1],
                       _state(done)))
    return _base(
        item, category,
        f"{label} vérifiée individuellement - repère {detail.get('map_id', '?')}, guide {detail.get('guide_id', '?')}.",
        detail.get("steps", ["Rejoins et résous l'énigme."])[0],
        "La noix doit être remise et le flag individuel du Korogu activé.", steps,
        tips=[f"Secteur cartographique {detail.get('map_unit', item.get('secteur', 'inconnu'))}."],
    )


def _tower_or_place(item: dict, category: str) -> dict:
    done = item.get("termine", False)
    if category == "tours":
        steps = [_step("Atteindre la tour", _position(item), _state(done, not done)),
                 _step("Grimper jusqu'au sommet", "Utilise les plateformes et gère l'endurance jusqu'au terminal.", _state(done, not done)),
                 _step("Examiner le terminal", "Insère la tablette Sheikah pour révéler la région.", _state(done))]
        return _base(item, category, "Tour Sheikah servant de point de téléportation et de révélation cartographique.",
                     "Atteins le sommet et active le terminal.", "Le flag d'activation de la tour doit être enregistré.", steps)
    steps = [_step("Rejoindre le lieu", _position(item), _state(done, not done)),
             _step("Entrer dans la zone de déclenchement", "Traverse la zone à pied jusqu'à voir son nom apparaître à l'écran.", _state(done, not done)),
             _step("Sauvegarder la découverte", "Attends l'enregistrement automatique ou effectue une sauvegarde.", _state(done))]
    return _base(item, category, "Lieu nommé participant au compteur officiel de la carte.",
                 "Entre précisément dans sa zone de découverte.", "Le flag Location de ce lieu doit être enregistré.", steps,
                 warnings=["Un simple survol en paravoile peut ne pas déclencher le nom du lieu."])


def _boss(item: dict, category: str) -> dict:
    done = item.get("termine", False)
    tactics = {
        "hinox": ("Vise l'œil pour l'étourdir, puis frappe ses jambes ou son corps pendant sa chute.", "Hinox"),
        "talus": ("Grimpe sur son corps et frappe le gisement ; détruis ses bras avec des bombes si nécessaire.", "Lithorok"),
        "moldarquors": ("Attire-le avec une bombe au sol, fais-la exploser lorsqu'il bondit puis attaque son ventre.", "Moldarquor"),
    }
    tactic, kind = tactics[category]
    steps = [_step(f"Trouver le {kind}", _position(item), _state(done, not done)),
             _step("Préparer le combat", "Équipe nourriture, armes et protections adaptées avant d'engager le combat.", _state(done, not done)),
             _step("Vaincre la créature", tactic, _state(done, not done)),
             _step("Enregistrer la victoire", "Ramasse les récompenses puis sauvegarde.", _state(done))]
    return _base(item, category, f"{kind} individuel suivi pour les médailles de Kilton.",
                 f"Rejoins et bats ce {kind}.", "Son flag individuel de défaite doit être enregistré.", steps,
                 warnings=["Une lune de sang peut faire réapparaître la créature, mais son premier flag de victoire reste acquis."])


def _compendium(item: dict, category: str) -> dict:
    done = item.get("termine", False)
    section = item.get("section") or "catégorie non renseignée"
    steps = [_step("Trouver le sujet", f"Cherche {item['name']} dans la section {section}.", _state(done, not done)),
             _step("Prendre une photo reconnue", "Cadre le sujet jusqu'à ce que son nom apparaisse, puis déclenche l'appareil photo.", _state(done, not done)),
             _step("Enregistrer l'entrée", "Vérifie que la nouvelle fiche apparaît dans le compendium.", _state(done))]
    return _base(item, category, f"Entrée n° {item.get('number', '-')} de la section {section} du compendium.",
                 "Photographie le sujet ou achète sa photo au laboratoire antique lorsque cette option est disponible.",
                 "Le flag IsRegisteredPictureBook propre à cette entrée doit être vrai.", steps,
                 tips=["Les photos achetées comptent comme les photos prises par Link."])


def _armor(item: dict, category: str) -> dict:
    owned = item.get("possede", False)
    level = item.get("niveau")
    maximal = category == "armures_max"
    upgrade = item.get("prochaine_amelioration")
    steps = [_step("Obtenir la pièce", f"Ajoute {item['name']} à la sacoche.", _state(owned, not owned))]
    if maximal:
        for target in range(1, 5):
            steps.append(_step(f"Amélioration {target} étoile{'s' if target > 1 else ''}",
                               "Présente la pièce et les matériaux requis à une Grande Fée débloquée.",
                               _state(level is not None and level >= target,
                                      level is not None and level == target - 1)))
    action = "Obtiens cette pièce d'armure."
    if maximal and owned and level is not None and level < 4:
        action = f"Prépare l'amélioration vers le niveau {level + 1}."
        if upgrade and upgrade.get("possible"):
            action += " Tous les matériaux nécessaires sont déjà dans la sacoche."
    condition = "La pièce doit être présente dans l'inventaire." if not maximal else "La variante exacte de niveau 4 doit être présente dans l'inventaire."
    return _base(item, category, f"Pièce de l'ensemble {item.get('set') or 'sans ensemble'}, emplacement {item.get('body_part') or 'inconnu'}.",
                 action, condition, steps,
                 warnings=["Les équipements amiibo peuvent dépendre d'un tirage aléatoire."] if item.get("amiibo") else [])


def _special(item: dict, category: str) -> dict:
    done = item.get("termine", False)
    action = item.get("action") or (
        f"Obtiens {item.get('name', 'cet objectif')} puis effectue une sauvegarde."
    )
    condition = item.get("completion_condition") or (
        "Le marqueur permanent correspondant doit être enregistré dans la sauvegarde."
    )
    steps = [
        _step("Rejoindre ou préparer l'objectif", _position(item), _state(done, not done)),
        _step("Accomplir l'objectif", action, _state(done, not done)),
        _step("Enregistrer la progression", "Effectue une sauvegarde normale après la validation.", _state(done)),
    ]
    return _base(
        item, category, "Objectif permanent ajouté au référentiel détaillé du compagnon.",
        action, condition, steps,
        warnings=["Cette vue peut recouper une quête déjà comptée ; le compagnon évite alors le double comptage."],
    )


def _dog_treasure(item: dict, category: str) -> dict:
    result = _base(
        item, category,
        f"Trésor indiqué par un chien à {item.get('location', 'cet endroit')}. Récompense : {item.get('reward', 'non renseignée')}.",
        "Donne au chien trois portions de nourriture adaptées, puis suis-le jusqu'au coffre.",
        "Coche manuellement cet objectif après avoir ouvert le coffre indiqué par le chien.",
        [_step("Rejoindre le chien", _position(item), "actuel", geo_point_index=0),
         _step("Gagner sa confiance", "Pose trois portions de viande ou de fruits près du chien et attends qu'il les mange."),
         _step("Suivre le chien", "Lorsqu'il commence à te guider, suis-le sans trop t'éloigner jusqu'au coffre."),
         _step("Ouvrir et cocher le trésor", f"Ouvre le coffre contenant {item.get('reward', 'sa récompense')}, puis utilise la case de suivi manuel.")],
        warnings=["La sauvegarde ne fournit pas de preuve permanente fiable pour ce trésor : seule ta case manuelle fait foi."],
    )
    result["completion"]["automatic"] = False
    result["completion"]["detection"] = "case locale persistante"
    return result


GuideBuilder = Callable[[dict, str], dict]


def _build_guide_v1(item: dict, category: str, flags: dict[str, object]) -> dict:
    """Retourne toujours une fiche individuelle, quelle que soit la catégorie."""
    if category in {"quetes_principales", "quetes_sanctuaires", "quetes_secondaires"}:
        return _quest(item, category, flags)
    if category in {"sanctuaires", "coffres_sanctuaires"}:
        return _shrine(item, category, flags)
    if category in {"coffres_monde", "coffres_donjons"}:
        return _chest(item, category)
    if category == "souvenirs":
        return _memory(item, category)
    if category == "korogus":
        return _korok(item, category)
    if category in {"tours", "lieux"}:
        return _tower_or_place(item, category)
    if category in {"hinox", "talus", "moldarquors"}:
        return _boss(item, category)
    if category == "compendium":
        return _compendium(item, category)
    if category in {"armures", "armures_max"}:
        return _armor(item, category)
    if category == "equipements_particuliers":
        return _base(
            item, category, "Pièce d'équipement particulière, non couverte par le suivi des armures améliorables.",
            f"Obtiens {item.get('name', 'cette pièce')} et conserve-la dans la sacoche.",
            "Une de ses variantes doit être présente dans l'inventaire.",
            [_step("Obtenir la pièce", _position(item), _state(item.get("termine", False), not item.get("termine", False))),
             _step("Vérifier la sacoche", "Ouvre l'onglet des armures et vérifie que la pièce est présente.", _state(item.get("termine", False)))],
        )
    if category in {"grandes_fees", "malanya", "epreuves_epee", "medailles_kilton",
                    "recompenses_uniques", "objets_speciaux", "creatures_divines",
                    "bosses_scenarises", "bonus_expansion", "ameliorations_prodiges"}:
        return _special(item, category)
    if category == "fonctionnalites_dlc":
        available = item.get("disponible", False)
        separate = item.get("feature") == "master_mode"
        return _base(
            item, category,
            "Fonctionnalité fournie par le premier pack de l'Expansion Pass.",
            "Ouvre une sauvegarde du mode Expert." if separate else
            "Ouvre la carte puis sélectionne le Mode Empreintes.",
            "L'Expansion Pass doit être détecté ; le mode Expert utilise une sauvegarde séparée.",
            [_step("Vérifier l'Expansion Pass", "Charge une sauvegarde créée avec l'Expansion Pass installé.",
                   _state(available, not available)),
             _step("Ouvrir la fonctionnalité",
                   "Choisis le mode Expert à l'écran-titre." if separate else
                   "Affiche la carte de la tablette Sheikah et active le Mode Empreintes.",
                   _state(item.get("utilise", False), available and not item.get("utilise", False)))],
            warnings=["Le mode Expert possède ses propres slots et ne doit pas être fusionné avec la progression normale."] if separate else [],
        )
    if category == "tresors_chiens":
        return _dog_treasure(item, category)
    # Garde-fou : toute future catégorie reçoit tout de même une fiche.
    done = item.get("termine", False)
    return _base(item, category, "Objectif individuel du catalogue BOTW.",
                 "Consulte ses métadonnées et accomplis l'action associée.",
                 "Son flag persistant doit être enregistré.",
                 [_step("Rejoindre l'objectif", _position(item), _state(done, not done)),
                  _step("Valider", "Accomplis l'objectif puis sauvegarde.", _state(done))],
                 warnings=["Cette catégorie utilise la fiche universelle de secours."])


def build_guide(item: dict, category: str, flags: dict[str, object]) -> dict:
    return enrich_guide(_build_guide_v1(item, category, flags), item, category)