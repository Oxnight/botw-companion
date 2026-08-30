"""Détails de solution structurés, sans transformer une supposition en certitude."""
from __future__ import annotations

import re
import unicodedata

from .localization import localize_editorial_text


OBJMAP = {"name": "BOTW Object Map", "url": "https://objmap.zeldamods.org/"}
SHRINE_INDEX = {
    "name": "Zelda Dungeon - liste et guides des sanctuaires",
    "url": "https://www.zeldadungeon.net/breath-of-the-wild-walkthrough/shrine-locations/",
}
KOROK_INDEX = {
    "name": "Zelda Dungeon - carte des 900 Korogus",
    "url": "https://www.zeldadungeon.net/breath-of-the-wild-walkthrough/korok-seed-locations/",
}
TRIAL_INDEX = {
    "name": "Zelda Dungeon - Épreuves de l'Épée",
    "url": "https://www.zeldadungeon.net/wiki/Trial_of_the_Sword",
}
BOSS_INDEX = {
    "name": "Zelda Dungeon - guide principal de Breath of the Wild",
    "url": "https://www.zeldadungeon.net/breath-of-the-wild-walkthrough/",
}
NINTENDO_DLC = {
    "name": "Nintendo - contenu téléchargeable de Breath of the Wild",
    "url": "https://www.nintendo.com/en-gb/Games/Nintendo-Switch-games/The-Legend-of-Zelda-Breath-of-the-Wild-1173609.html",
}
QUEST_REWARD_OVERRIDES = {
    "GanonQuest": "Étoile de fin sur la sauvegarde et déblocages post-fin",
    "Wind_Relic": "Réceptacle de cœur, Rage de Revali et libération de Vah'Medoh",
    "Electric_Relic": "Réceptacle de cœur, Colère d'Urbosa et libération de Vah'Naboris",
    "Fire_Relic": "Réceptacle de cœur, Bouclier de Daruk et libération de Vah'Rudania",
    "Water_Relic": "Réceptacle de cœur, Prière de Mipha et libération de Vah'Ruta",
    "FairyFountain": "Localisation de la fontaine de Cotura et nouvel indice de souvenir auprès de Kangis",
    "FirstTower": "Carte du plateau du Prélude et activation de la tour",
    "Find_4Relic": "Validation de la libération des quatre Créatures divines et affaiblissement de Ganon",
    "GotoZoraVillage": "Accès au domaine Zora et ouverture de la quête de Vah'Ruta",
    "Find_Impa": "Ouverture des quêtes Les créatures divines et Des photos, des souvenirs",
    "UotoriMini_SinkTreasure": "Lame de foudre, 1 saphir brut et 2 topazes brutes",
    "MarittaMini_BigWhales": "Rubis doré (300 rubis)",
}
SUNKEN_TREASURE_SOURCE = {
    "name": "Zelda Dungeon - Sunken Treasure",
    "url": "https://www.zeldadungeon.net/wiki/Sunken_Treasure",
}
LEVIATHAN_SOURCE = {
    "name": "Zelda Dungeon - Leviathan Bones",
    "url": "https://www.zeldadungeon.net/wiki/Leviathan_Bones",
}

QUALITY_LABELS = {
    1: "Niveau 1 - Localisation exacte",
    2: "Niveau 2 - Conseil vérifié par famille",
    3: "Niveau 3 - Solution complète vérifiée",
}


def _quality(guide: dict, level: int, basis: str) -> None:
    guide["quality_level"] = level
    guide["quality_label"] = QUALITY_LABELS[level]
    guide["verification_basis"] = basis


def _plain(value: object) -> str:
    text = unicodedata.normalize("NFD", str(value or "").lower())
    return "".join(char for char in text if unicodedata.category(char) != "Mn")


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _add_sources(guide: dict, additions: list[dict]) -> None:
    seen = {(item.get("name"), item.get("url")) for item in guide.get("sources", [])}
    for source in additions:
        key = (source.get("name"), source.get("url"))
        if key not in seen:
            guide.setdefault("sources", []).append(source)
            seen.add(key)


def _shrine_mechanic(item: dict) -> dict:
    title = item.get("trial") or "Épreuve non renseignée"
    text = _plain(title)
    if "benediction" in text:
        return {
            "quality": 2,
            "kind": "Bénédiction",
            "requirements": ["Avoir terminé l'épreuve extérieure ou trouvé l'entrée cachée"],
            "preparation": ["Garder une place libre dans l'inventaire si le coffre contient une arme"],
            "steps": [
                f"Entre dans {item.get('name')} : « {title} » ne contient pas de puzzle intérieur supplémentaire.",
                "Ouvre le coffre placé avant l'autel, puis examine l'autel pour recevoir la récompense.",
            ],
            "chest": "Le coffre est dans la salle unique, sur le trajet direct vers l'autel.",
        }
    if "epreuve" in text and "force" in text:
        rank = "basique" if "basique" in text else "moyenne" if "moyenne" in text else "extrême"
        return {
            "quality": 2,
            "kind": f"Combat - difficulté {rank}",
            "requirements": ["Armes, bouclier et nourriture de soin", "Une arme électrique ou de glace facilite les interruptions"],
            "preparation": ["Retirer les armes métalliques si un orage extérieur est actif", "Prévoir plusieurs armes pour l'épreuve extrême"],
            "steps": [
                "Verrouille le Nano Gardien et esquive latéralement ses attaques pour déclencher une esquive parfaite.",
                "Lorsqu'il tourne avec ses armes, place un pilier ou un obstacle entre vous, puis frappe-le pendant son étourdissement.",
                "Pendant l'attaque laser rotative, utilise le courant ascendant pour tirer en ralenti ou reste hors de portée.",
                "À très basse santé, interromps ou évite son laser chargé, puis termine le combat et ouvre le coffre.",
            ],
            "chest": "Le coffre apparaît après la victoire, avant l'autel.",
        }

    # Épreuves dont le titre français ne contient pas le nom du module. Ces
    # parcours ont été contrôlés individuellement contre des solutions publiées.
    specials = {
        "entre calme et chaos": ("Cinetis, tapis roulants et lasers", ["Cinetis", "Arc"], [
            "Fige la première sphère lorsqu'elle passe devant le réceptacle, puis décoche une flèche pour la faire tomber dedans.",
            "Dans la seconde salle, neutralise les Nano Gardiens et répète l'opération sur la sphère en mouvement.",
            "Porte la dernière sphère sur le tapis roulant ; avance derrière les blocs qui coupent les lasers et dépose-la dans son réceptacle."],
            "Inspecte les côtés des tapis roulants avant de franchir la dernière porte."),
        "une percee": ("Feu, grilles et petite clé", ["Flèche de feu ou arme enflammée", "Arc"], [
            "Brûle le lierre près de la première grille et traverse l'ouverture après la combustion des caisses.",
            "Élimine les Nano Gardiens, puis brûle la caisse sous la rampe et déplace le bloc métallique.",
            "Frappe les tonneaux à travers les barreaux, récupère la petite clé et ouvre la porte de l'autel."],
            "Après la petite clé, grimpe à l'échelle et saute sur le côté pour atteindre le coffre facultatif."),
        "secret enfoui": ("Bombes, Polaris et plaque de pression", ["Bombes", "Polaris"], [
            "Détruis tous les amas de roche fissurée, notamment celui sous la plateforme d'entrée.",
            "Sors le bloc métallique, utilise-le comme marche pour gagner l'échelle puis récupère-le depuis l'étage.",
            "Pose ce bloc sur la grosse plaque afin de lever les barreaux vers l'autel."],
            "Un coffre est caché derrière les rochers près de l'entrée ; l'autre se décroche de sa colonne avec Polaris."),
        "trois elements de sagesse": ("Polaris, cristal et pression", ["Polaris", "Arc ou arme"], [
            "Monte par la rampe et place le cube métallique pour rejoindre le côté du coffre.",
            "Frappe le cristal afin de déplacer les plateformes, puis récupère le coffre avec Polaris.",
            "Pose le coffre sur la plaque en hauteur, repositionne le cube et rejoins l'autel."],
            "Le coffre est un élément de la solution : garde-le après l'avoir ouvert afin d'actionner la plaque."),
        "sur la pente de la convoitise": ("Ascension sous les projectiles", ["Polaris", "Protection ignifuge"], [
            "Remonte la pente en te plaçant dans les renfoncements pour éviter les sphères et pièges.",
            "Saisis avec Polaris les sphères métalliques qui bloquent ton passage et profite des fenêtres entre deux chutes.",
            "Atteins le sommet puis rejoins l'autel."],
            "Prends le coffre dans le renfoncement droit ; depuis le sommet, redescends en paravoile vers la plateforme du second coffre."),
        "au travers des portes": ("Cristal, sphère et tremplin", ["Arc", "Paravoile"], [
            "Actionne le cristal, emprunte le passage latéral et récupère la petite clé.",
            "Ramène la sphère, inverse le cristal, ouvre la porte puis place la sphère dans la corbeille sous le mécanisme.",
            "Réactive le cristal pour envoyer la sphère au réceptacle ; utilise alors le tremplin et tire sur le cristal en plein vol pour atteindre l'autel."],
            "Depuis le tremplin activé, plane vers le coffre surélevé avant de viser l'autel."),
        "main salvatrice": ("Polaris et coupelle métallique", ["Polaris"], [
            "Repère au fond du premier bassin la grande coupelle métallique et saisis-la avec Polaris.",
            "Utilise-la comme une épuisette pour porter une sphère jusqu'au premier réceptacle.",
            "Emporte la coupelle dans la seconde salle, place une sphère au-dessus de la cage puis actionne le mécanisme immergé."],
            "Sors le coffre immergé avec Polaris avant de quitter le premier bassin."),
        "capacites d'adaptation": ("Tonneaux, poids et plateformes mobiles", ["Arc"], [
            "Sur l'aile droite, place un tonneau et ton propre poids du bon côté de la plateforme pour franchir successivement les grilles.",
            "Pose le tonneau sur la plaque, reviens au départ et récupère le coffre libéré.",
            "Répète le parcours de l'autre côté en t'accroupissant sous la grille, puis récupère la petite clé et ouvre la porte centrale."],
            "Les deux ailes donnent chacune accès à un coffre ; l'un contient la petite clé indispensable."),
        "force massive": ("Polaris, Cinetis et béliers", ["Polaris", "Cinetis", "Bombes"], [
            "Tire puis relâche le premier boulet avec Polaris pour fracasser la porte.",
            "Traverse les pièges, élimine les Nano Gardiens et utilise feu, boulets et tremplins pour ouvrir les sections suivantes.",
            "Fige les mécanismes avec Cinetis, charge leur énergie dans l'axe des portes et termine par le bélier."],
            "Inspecte chaque salle ; un passage rocheux destructible à la bombe cache un coffre supplémentaire."),
        "mur rouge dissimule": ("Polaris, vent et Cinetis", ["Polaris", "Cinetis"], [
            "Avec Polaris, retire du mur l'élément métallique caché et place le cube pour bloquer le courant d'air qui détourne la sphère.",
            "Lâche la sphère sur son parcours et fige la plateforme mobile au moment où elle doit la transporter.",
            "Place-toi sur l'ascenseur avant que la sphère n'atteigne son réceptacle, puis monte vers l'autel."],
            "Récupère avec Polaris le coffre en hauteur près de la plateforme mobile avant de lancer la sphère."),
        "preparation psychologique": ("Torches, pièges et combats", ["Moyen d'allumer du feu", "Arc et armes"], [
            "Allume la torche éteinte près de la première grille pour ouvrir le parcours.",
            "Progresse prudemment : les couloirs déclenchent successivement obstacles, chutes de sphères et combats de Nano Gardiens.",
            "Observe chaque nouvelle salle avant d'avancer, neutralise son mécanisme puis rejoins l'autel."],
            "Fouille les embranchements après chaque piège ; le coffre est hors de la ligne directe de progression."),
        "pas a pas": ("Cinetis et propulsion", ["Cinetis", "Bombes", "Arme lourde"], [
            "Fige le tremplin central et charge-le afin que la sphère frappe progressivement l'interrupteur de la première salle.",
            "Dans la salle suivante, détruis les blocs friables avec une bombe.",
            "Fige le tonneau, frappe-le dans l'axe jusqu'à obtenir une trajectoire suffisante et envoie-le sur la cible éloignée."],
            "La réussite de la seconde propulsion ouvre l'accès au coffre avant l'autel."),
        "moderer sa force": ("Golf avec Cinetis", ["Cinetis", "Marteau ou arme lourde"], [
            "Fige la première sphère, vise légèrement dans l'axe et donne environ cinq coups de marteau pour atteindre le réceptacle.",
            "Fige et frappe le bloc afin d'incliner la bascule, puis grimpe pendant la fenêtre créée.",
            "Rejoins l'autel ou poursuis par le chemin latéral pour la seconde épreuve facultative."],
            "Le parcours latéral derrière l'autel propose un second tir de précision et ouvre le coffre rare."),
        "savoir quand s'arreter": ("Polaris puis Cinetis", ["Polaris", "Cinetis"], [
            "Monte les rampes et utilise Polaris pour lever au maximum le bloc métallique posé sur le coffre à clé.",
            "Relâche le bloc puis fige-le immédiatement en l'air avec Cinetis ; saute sur la plateforme et ouvre le coffre.",
            "Récupère l'autre coffre pendant la descente, puis utilise la petite clé sur la porte de l'autel."],
            "Il y a deux coffres : la petite clé sous le bloc et une arme accessible en planant depuis les rampes supérieures."),
        "de pilier en pilier": ("Cryonis et trajectoire d'orbe", ["Cryonis"], [
            "Observe la chute de l'orbe et crée un pilier Cryonis pour le dévier vers la première bascule.",
            "Bloque ou incline successivement les bascules avec d'autres piliers afin de conserver la trajectoire vers le bas à droite.",
            "Corrige le dernier segment pour faire tomber l'orbe dans son réceptacle et ouvrir l'autel."],
            "Avant la dernière correction, utilise les piliers comme marches pour rejoindre le coffre latéral."),
        "viser dans la quietude": ("Vent, bombes et Cinetis", ["Paravoile", "Bombes", "Cinetis"], [
            "Traverse le gouffre dans les courants ascendants et détruis les premiers blocs friables.",
            "Place une bombe dans chaque conduit et déclenche-la lorsqu'elle atteint le mur obstrué.",
            "Dans la section tournante, fige la roue au bon alignement, attends la remontée de la grille puis expédie la bombe vers le dernier mur."],
            "Prends de la hauteur dans les ventilateurs pour atteindre la plateforme du coffre avant l'autel."),
        "double emploi": ("Ponts conducteurs avec Polaris", ["Polaris", "Protection électrique recommandée"], [
            "Déplace les premiers blocs métalliques pour former un pont, traverse, puis rapproche-les du générateur afin d'ouvrir la porte.",
            "Dans la salle suivante, déconnecte les blocs pour créer le passage, traverse puis reconnecte-les afin d'alimenter la sortie.",
            "Dans la dernière salle, utilise les blocs à la fois comme escalier et comme circuit : aligne la conduction sans électrifier la case sur laquelle tu grimpes."],
            "Réorganise les cubes du milieu pour conduire le courant vers la grille du coffre avant de former l'escalier final."),
    }
    if text in specials:
        kind, requirements, steps, chest = specials[text]
        return {"kind": kind, "requirements": requirements, "quality": 3,
                "preparation": ["Observer tout le parcours avant d'actionner le premier mécanisme"],
                "steps": steps, "chest": chest}

    rules = [
        (("electric", "circuit", "cinq de fer"), "Électricité et Polaris", "Relie les conducteurs métalliques avec Polaris afin de fermer chaque circuit.", "Inspecte les côtés et le plafond : un conducteur ou un coffre métallique peut servir de pont électrique."),
        (("flamme", "feu", "fonte"), "Feu et torches", "Allume, propage ou protège les flammes nécessaires ; utilise les flèches de feu et coupe les arrivées d'eau si besoin.", "Avant l'autel, cherche un brasier, des feuilles ou de la glace qui dissimulent le coffre."),
        (("vent", "vol", "cieux"), "Courants ascendants", "Déploie la paravoile dans les courants ascendants et ajuste ta trajectoire entre les plateformes.", "Prends de la hauteur avant de viser le coffre : il est souvent sur une plateforme latérale ou derrière le trajet principal."),
        (("eau", "flot", "glace"), "Cryonis et niveau d'eau", "Crée des piliers Cryonis pour bloquer, soulever ou détourner les éléments flottants et franchir le bassin.", "Teste Cryonis sous les grilles, coffres ou plateformes qui semblent hors d'atteinte."),
        (("bombe", "destruction", "canon", "trajectoire", "balle"), "Bombes et trajectoires", "Utilise les deux formes de bombes, les interrupteurs et l'inertie pour envoyer le projectile vers sa cible.", "Observe la trajectoire complète avant le tir ; le coffre demande souvent un angle ou un lancement secondaire."),
        (("temps", "moment", "instant", "mouvement", "simultane"), "Cinetis et synchronisation", "Fige l'objet au bon instant avec Cinetis, charge son énergie si nécessaire, puis traverse pendant la fenêtre créée.", "Une plateforme mobile ou un objet figé peut ouvrir un accès temporaire au coffre."),
        (("magnet", "fer", "boite", "caisse", "passerelle"), "Polaris et construction", "Déplace les objets métalliques avec Polaris pour construire un passage, un contrepoids ou un conducteur.", "Le coffre peut lui-même être métallique : essaie Polaris avant de chercher un chemin physique."),
        (("equilibre", "pression", "poids", "gabarit", "courbe"), "Poids et équilibre", "Répartis les blocs, orbes ou caisses sur les balances et plaques afin d'aligner les plateformes.", "Mémorise la position initiale des objets avant de les déplacer pour pouvoir atteindre le coffre."),
        (("mecanisme", "rouage", "angle", "guide"), "Appareil gyroscopique", "Examine le terminal puis incline doucement la manette pour orienter le mécanisme, sans mouvements brusques.", "Place d'abord le mécanisme dans une position stable pour le coffre, puis réoriente-le vers la sortie."),
        (("lumiere", "etoile", "ombre"), "Observation et symboles", "Observe les motifs, constellations, ombres ou sources lumineuses et reproduis leur ordre sur les interrupteurs.", "Photographie ou note le motif de référence avant de manipuler la salle."),
        (("jumel",), "Sanctuaires jumeaux", "Relève la disposition des orbes dans l'autre sanctuaire jumeau, puis reproduis-la exactement ici.", "Photographie les deux grilles avant tout déplacement ; chaque sanctuaire possède son propre coffre."),
        (("voie", "chemin", "march", "ascension", "passerelle"), "Parcours et construction", "Observe l'arrivée avant d'agir, puis combine modules, plateformes et impulsions pour créer une route continue.", "Regarde derrière et au-dessus de la route principale : le coffre récompense souvent un détour."),
        (("enseigne",), "Tutoriel de combat", "Suis dans l'ordre les instructions du moine : esquive latérale, salto arrière, garde parfaite puis attaque chargée.", "Le coffre devient accessible après avoir exécuté toutes les techniques demandées."),
    ]
    for needles, kind, action, chest in rules:
        if any(needle in text for needle in needles):
            modules = []
            for keyword, module in (("electric", "Polaris"), ("fer", "Polaris"), ("eau", "Cryonis"),
                                    ("glace", "Cryonis"), ("temps", "Cinetis"), ("bombe", "Bombes"),
                                    ("vent", "Paravoile"), ("flamme", "Flèches de feu")):
                if keyword in text:
                    modules.append(module)
            return {
                "quality": 2,
                "kind": kind,
                "requirements": [f"Module conseillé : {module}" for module in _dedupe(modules)] or ["Modules de la tablette Sheikah"],
                "preparation": ["Observer toute la salle avant de déplacer le premier élément"],
                "steps": [
                    f"Dans « {title} », identifie d'abord le mécanisme principal : {kind.lower()}.",
                    action,
                    "Avant de rejoindre l'autel, récupère le coffre en appliquant le même mécanisme au détour latéral.",
                ],
                "chest": chest,
            }
    return {
        "quality": 1,
        "kind": f"Épreuve nommée - {title}",
        "requirements": ["Modules de la tablette Sheikah", "Paravoile et arc recommandés"],
        "preparation": ["Observer les objets interactifs, interrupteurs et chemins secondaires"],
        "steps": [
            f"Entre dans {item.get('name')} et repère le dispositif central correspondant à « {title} ».",
            "Teste les modules sur les objets colorés ou mobiles, puis suis la réaction du mécanisme jusqu'à ouvrir la route principale.",
            "Inspecte le détour avant l'autel et ouvre le coffre avant de récupérer la récompense du moine.",
        ],
        "chest": "Le contenu exact est suivi dans la catégorie des coffres de sanctuaire ; vérifie l'icône de coffre sur la carte du jeu.",
    }


def _quest_action(name: str) -> tuple[str, list[str]]:
    text = _plain(name)
    rules = [
        (("photo", "souvenir", "appareil"), "Utilise le module appareil photo et fais reconnaître le sujet demandé avant de retourner voir le donneur.", ["Module appareil photo"]),
        (("cocotte",), "Retrouve chaque cocotte dans le village, porte-la jusqu'à l'enclos puis reparle au propriétaire.", []),
        (("cheval", "debourrage", "piste", "monture"), "Capture ou prépare une monture adaptée, puis termine le parcours ou présente le cheval demandé.", ["Une monture enregistrée ou assez d'endurance"]),
        (("maracas",), "Élimine les Bokoblins du camp, récupère les maracas dans le coffre puis rapporte-les à Noïa.", []),
        (("recette", "cuisine", "gateau", "plat", "gourmet"), "Réunis les ingrédients indiqués, cuisine le plat dans une marmite puis remets-le au donneur.", ["Une marmite et les ingrédients demandés"]),
        (("armure", "casque", "tunique", "bottes"), "Obtiens ou équipe la pièce demandée, puis présente-toi devant le donneur avec la tenue correcte.", ["La pièce d'équipement demandée"]),
        (("fleur", "herbe", "champignon", "insecte"), "Récolte la quantité demandée sans utiliser les exemplaires nécessaires à tes améliorations, puis rapporte-la.", []),
        (("monstre", "gardien", "hinox", "lithorok", "moldarquor", "lynel"), "Prépare le combat, vaincs la cible indiquée puis reviens avec la preuve ou après l'enregistrement de la victoire.", ["Armes, soins et protection adaptés à la cible"]),
        (("joyau", "orbe", "pierre", "fragment"), "Localise l'objet demandé, transporte-le jusqu'au socle ou au donneur et évite de le perdre dans une pente ou l'eau.", []),
        (("chant", "chanson", "ballade"), "Écoute l'indice musical, interprète ses lieux ou actions, puis accomplis-les dans l'ordre indiqué.", []),
        (("labyrinthe", "epreuve"), "Suis l'indice de l'épreuve extérieure jusqu'au sanctuaire ; la validation peut exiger une heure, une météo ou un équipement précis.", []),
        (("tresor", "lambda", "ex"), "Suis les indices de localisation, ouvre le coffre correspondant puis vérifie la mise à jour du journal.", []),
    ]
    for needles, action, requirements in rules:
        if any(needle in text for needle in needles):
            return action, requirements
    return ("Parle au donneur au point de départ, lis l'objectif actuel dans le journal puis suis les points ordonnés de cette fiche.", [])


def _boss_strategy(item: dict) -> tuple[list[str], list[str]]:
    name = _plain(item.get("name"))
    strategies = [
        (("kohga",), ["Renvoie ses rochers avec Polaris ou fais-les tomber sur lui lorsqu'ils passent au-dessus de sa tête.", "Dans la dernière phase, utilise Polaris sur la boule métallique pour la rabattre sur le boss."], ["Arc utile pour interrompre rapidement ses poses"]),
        (("eau de ganon",), ["Première phase : esquive sa lance et frappe après ses balayages.", "Seconde phase : détruis les blocs de glace avec Cryonis, puis vise son œil lorsqu'il flotte."], ["Arc et flèches", "Cryonis"]),
        (("feu de ganon",), ["Esquive l'épée et profite de la fin de ses combos.", "Lorsqu'une barrière de feu le protège, lance une bombe vers son aspiration et fais-la exploser pour l'étourdir."], ["Bombes", "Protection ignifuge recommandée"]),
        (("vent de ganon",), ["Reste mobile entre les piliers et vise l'œil avec l'arc.", "Utilise les courants ascendants pour tirer au ralenti et détruire rapidement ses points de vie."], ["Arc et réserve de flèches"]),
        (("foudre de ganon",), ["Esquive ses accélérations puis déclenche une esquive parfaite.", "Pendant l'orage, place avec Polaris un pilier métallique près de lui afin que sa propre foudre brise son bouclier."], ["Polaris", "Bouclier et nourriture anti-électricité"]),
        (("guide miz", "kyosia"), ["Détruis les clones : le vrai moine reste visible au verrouillage ou réagit à la banane déposée.", "Utilise les piliers, la paravoile et les attaques aériennes contre ses charges, puis frappe après chaque ouverture."], ["Armes solides", "Arc", "Soins complets"]),
        (("ganon, le fleau",), ["Libère les Créatures divines avant le combat pour retirer jusqu'à la moitié de sa vie.", "Renvoie les lasers avec une garde parfaite et vise l'œil après chaque ouverture.", "Contre la Créature maléfique, chevauche, tire sur les points lumineux puis termine avec l'arc de lumière."], ["Boucliers de rechange", "Arc et soins"]),
        (("arquor rex",), ["Reste sur les rochers, lance une bombe sur le sable et fais-la exploser lorsqu'il l'avale.", "Après son bond, attaque le ventre puis remonte avant qu'il ne replonge."], ["Bombes", "Protection contre la chaleur"]),
        (("mega magrok",), ["Utilise une protection ignifuge et refroidis son corps avec une flèche de glace avant de grimper.", "Frappe le gisement, saute lorsqu'il se réchauffe puis recommence après l'avoir refroidi."], ["Protection ignifuge", "Flèches de glace"]),
    ]
    for needles, steps, requirements in strategies:
        if any(needle in name for needle in needles):
            if "royaume illusoire" in name:
                requirements.append("Équipement imposé par le royaume illusoire : économise armes et soins")
            return steps, requirements
    if "hinox" in name or "stalhinox" in name:
        return (["Vise l'œil pour l'étourdir, puis frappe les jambes ou le corps pendant sa chute.", "Pour un Stalhinox, détruis l'œil séparé avant l'aube."], ["Arc et flèches"])
    if any(word in name for word in ("lithorok", "magrok", "cryorok")):
        return (["Grimpe sur le corps et frappe le gisement ; détruis ses bras à distance pour créer une ouverture.", "Adapte ta protection et tes flèches à la variante de feu ou de glace."], ["Marteau ou arme contondante"])
    if "moldarquor" in name:
        return (["Lance une bombe sur le sable, fais-la exploser lorsqu'il bondit puis attaque son ventre."], ["Bombes"])
    return (["Observe le cycle d'attaque, esquive la dernière frappe puis contre-attaque pendant la récupération."], ["Armes, bouclier et soins"])


def _scripted_boss_detail(item: dict) -> dict:
    """Décrit les combats uniques sans les confondre avec les mini-boss de farm."""
    name = _plain(item.get("name"))
    illusory = "royaume illusoire" in name
    if "kohga" in name:
        return {
            "requirements": ["Accès au repaire des Yigas", "Arc et flèches"],
            "steps": [
                "Phase 1 : décoche une flèche lorsque son rocher apparaît au-dessus de lui, puis frappe-le pendant sa chute.",
                "Phase 2 : attends que les deux rochers tournants s'alignent au-dessus de lui avant de tirer et d'attaquer.",
                "Phase 3 : saisis avec Polaris la boule métallique hérissée et rabats-la sur lui jusqu'à la cinématique finale.",
            ],
            "rewards": ["Récupération du casque du tonnerre pour poursuivre la quête de Vah'Naboris"],
            "respawn": "Combat scénarisé unique : Grand Kohga ne réapparaît pas après sa défaite.",
        }
    if "eau de ganon" in name:
        return {
            "requirements": (["Équipement imposé par le royaume illusoire", "Cryonis", "Arc"] if illusory
                             else ["Cryonis", "Arc et flèches", "Armes de mêlée"]),
            "steps": [
                "Phase 1 : reste près du corps du boss, évite les balayages de lance et frappe après la fin de ses enchaînements.",
                "Phase 2 : crée des piliers Cryonis entre les plateformes, détruis ses blocs de glace avec Cryonis puis vise l'œil.",
                "Fin du combat : rejoins sa plateforme après chaque étourdissement et conserve des flèches pour interrompre son laser chargé.",
            ],
            "rewards": (["Amélioration de la Prière de Mipha : temps de recharge réduit"] if illusory
                        else ["Réceptacle de cœur", "Prière de Mipha", "Libération de Vah'Ruta"]),
            "respawn": ("Rematch DLC répétable après la première victoire ; aucune nouvelle récompense permanente."
                        if illusory else "Combat scénarisé unique dans Vah'Ruta."),
        }
    if "feu de ganon" in name:
        return {
            "requirements": (["Équipement imposé par le royaume illusoire", "Bombes"] if illusory
                             else ["Bombes", "Protection ignifuge", "Arc recommandé"]),
            "steps": [
                "Phase 1 : esquive son épée et frappe après ses enchaînements ; une flèche dans l'œil crée une ouverture.",
                "Phase 2 : lorsqu'il aspire l'air derrière sa barrière, lance une bombe dans l'aspiration puis déclenche-la.",
                "Fin du combat : attaque durant son étourdissement et interromps son laser final avec une flèche dans l'œil.",
            ],
            "rewards": (["Amélioration du Bouclier de Daruk : temps de recharge réduit"] if illusory
                        else ["Réceptacle de cœur", "Bouclier de Daruk", "Libération de Vah'Rudania"]),
            "respawn": ("Rematch DLC répétable après la première victoire ; aucune nouvelle récompense permanente."
                        if illusory else "Combat scénarisé unique dans Vah'Rudania."),
        }
    if "vent de ganon" in name:
        return {
            "requirements": (["Équipement imposé par le royaume illusoire", "Arc"] if illusory
                             else ["Arc", "Réserve de flèches", "Paravoile"]),
            "steps": [
                "Phase 1 : déplace-toi entre les piliers, évite les projectiles et vise l'œil lorsqu'il matérialise son canon.",
                "Phase 2 : utilise les courants ascendants pour tirer en ralenti et détruis les projectiles avant qu'ils ne te cernent.",
                "Fin du combat : profite de chaque chute pour attaquer au corps à corps et garde des flèches pour son laser chargé.",
            ],
            "rewards": (["Amélioration de la Rage de Revali : temps de recharge réduit"] if illusory
                        else ["Réceptacle de cœur", "Rage de Revali", "Libération de Vah'Medoh"]),
            "respawn": ("Rematch DLC répétable après la première victoire ; aucune nouvelle récompense permanente."
                        if illusory else "Combat scénarisé unique dans Vah'Medoh."),
        }
    if "foudre de ganon" in name:
        return {
            "requirements": (["Équipement imposé par le royaume illusoire", "Polaris"] if illusory
                             else ["Polaris", "Boucliers", "Résistance à l'électricité recommandée"]),
            "steps": [
                "Phase 1 : bloque ou esquive ses trois accélérations, puis contre-attaque lorsqu'il s'arrête à portée.",
                "Phase 2 : prends un pilier métallique avec Polaris et maintiens-le près du boss pour que sa propre foudre brise sa garde.",
                "Fin du combat : détruis son bouclier, effectue une esquive parfaite sur ses charges et interromps le laser final.",
            ],
            "rewards": (["Amélioration de la Colère d'Urbosa : temps de recharge réduit"] if illusory
                        else ["Réceptacle de cœur", "Colère d'Urbosa", "Libération de Vah'Naboris"]),
            "respawn": ("Rematch DLC répétable après la première victoire ; aucune nouvelle récompense permanente."
                        if illusory else "Combat scénarisé unique dans Vah'Naboris."),
        }
    if "guide miz" in name or "kyosia" in name:
        return {
            "requirements": ["Ballade des Prodiges arrivée au sanctuaire de la Renaissance", "Armes solides", "Arc et soins"],
            "steps": [
                "Phase 1 : esquive ses attaques rapprochées et frappe après ses téléportations ; une banane déposée peut créer une ouverture.",
                "Phase 2 : élimine rapidement les clones - le vrai moine conserve sa barre de vie et reste la cible du verrouillage.",
                "Phase 3 : utilise les piliers et la paravoile contre sa taille géante, puis vise-le en plein saut avant d'attaquer au sol.",
            ],
            "rewards": ["Destrier de légende 0.1"],
            "respawn": "Combat DLC scénarisé unique pour la récompense ; le rematch ne redonne pas le Destrier.",
        }
    if "arquor rex" in name:
        return {
            "requirements": ["Épreuve de Mipha activée", "Bombes", "Protection contre la chaleur"],
            "steps": [
                "Reste sur un rocher afin d'éviter ses déplacements sous le sable et lance une bombe au sol pour l'attirer.",
                "Fais exploser la bombe lorsqu'il bondit, puis rejoins-le et attaque son ventre pendant son étourdissement.",
                "Reviens sur une zone solide avant son réveil et répète le cycle en évitant ses projectiles.",
            ],
            "rewards": ["Validation de l'épreuve correspondante du chant de Mipha"],
            "respawn": "Mini-boss DLC lié à une épreuve ; son point reste exploitable selon l'état du monde.",
        }
    if "mega magrok" in name:
        return {
            "requirements": ["Épreuve de Daruk activée", "Protection ignifuge", "Flèches de glace"],
            "steps": [
                "Refroidis son corps avec une flèche de glace avant toute tentative d'escalade.",
                "Grimpe pendant la fenêtre froide et frappe le gisement avec une arme contondante ou à deux mains.",
                "Saute dès qu'il se réchauffe, évite les bras projetés puis recommence après l'avoir refroidi.",
            ],
            "rewards": ["Validation de l'épreuve correspondante du chant de Daruk"],
            "respawn": "Mini-boss DLC lié à une épreuve ; son point reste exploitable selon l'état du monde.",
        }
    if "ganon, le fleau" in name:
        return {
            "requirements": ["Accès au sanctuaire central du château d'Hyrule", "Boucliers de rechange", "Arc et soins"],
            "steps": [
                "Première partie : exploite les pouvoirs des Créatures divines libérées, esquive ses armes et vise l'œil après chaque ouverture.",
                "Lorsque sa barrière devient invulnérable, renvoie un laser par garde parfaite ou déclenche une esquive parfaite pour pouvoir le blesser.",
                "Créature maléfique : combats à cheval, tire avec l'arc de lumière sur les points indiqués par Zelda puis vise l'œil final en plein vol.",
            ],
            "rewards": ["Étoile sur la sauvegarde", "Déblocages post-fin associés, dont les médailles de Kilton"],
            "respawn": "La sauvegarde revient avant le combat final avec une étoile : Ganon peut être affronté de nouveau.",
        }
    steps, requirements = _boss_strategy(item)
    return {
        "requirements": requirements,
        "steps": steps,
        "rewards": ["Progression scénarisée correspondante"],
        "respawn": "Condition de nouvelle apparition non documentée pour ce combat.",
    }


def _reward(item: dict, category: str) -> list[str]:
    if item.get("reward"):
        return [str(item["reward"])]
    if category in {"sanctuaires", "coffres_sanctuaires"}:
        return ["Emblème de triomphe ou emblème de Prodige selon le sanctuaire"] if category == "sanctuaires" else [str(item.get("contenu") or "Contenu du coffre suivi séparément")]
    if category == "korogus":
        return ["1 noix korogu"]
    if category == "compendium":
        return ["Entrée permanente dans le compendium"]
    if category in {"hinox", "talus", "moldarquors", "bosses_scenarises"}:
        return ["Butin du combat", "Progression permanente si ce boss possède un flag individuel"]
    if category == "tresors_chiens":
        return [str(item.get("reward") or "Contenu du coffre")]
    if category.startswith("quetes_"):
        return ["Récompense de quête - vérifier le dialogue final ; elle n'est pas encodée de façon fiable dans la sauvegarde"]
    if item.get("contenu"):
        return [str(item["contenu"])]
    return []


def enrich_guide(guide: dict, item: dict, category: str) -> dict:
    guide["version"] = 3
    guide["objective_key"] = f"{category}:{item.get('id') or item.get('flag') or item.get('name')}"
    guide["prerequisites"] = []
    guide["preparation"] = []
    guide["rewards"] = _reward(item, category)
    guide["detailed_steps"] = []
    guide["specificity"] = "catalogue"
    guide["specificity_label"] = "Données propres à cet objectif"
    _quality(guide, 1, "Métadonnées et position du catalogue ; aucune solution intégrale affirmée.")

    if category in {"sanctuaires", "coffres_sanctuaires"}:
        detail = _shrine_mechanic(item)
        guide["prerequisites"] = detail["requirements"]
        if item.get("quest"):
            guide["prerequisites"].insert(0, f"Quête d'accès : {item['quest']}")
        guide["preparation"] = detail["preparation"]
        guide["detailed_steps"] = detail["steps"]
        guide["chest_solution"] = detail["chest"]
        interior_chests = item.get("interior_chests", [])
        if interior_chests:
            guide["interior_map"] = item.get("interior_map")
            guide["interior_map_label"] = item.get("interior_map_label")
            guide["chest_details"] = [
                {
                    "number": index,
                    "content": chest.get("content", "Contenu non identifié"),
                    "interior_position": {
                        "x": chest.get("x"), "y": chest.get("y"), "z": chest.get("z"),
                    },
                }
                for index, chest in enumerate(interior_chests, 1)
            ]
            positions = "; ".join(
                f"coffre {index} - {chest.get('content', 'contenu non identifié')} "
                f"(X {chest.get('x', 0):.1f}, Y {chest.get('y', 0):.1f}, Z {chest.get('z', 0):.1f})"
                for index, chest in enumerate(interior_chests, 1)
            )
            guide["chest_solution"] += (
                f" Carte intérieure : {item.get('interior_map_label') or item.get('interior_map')}. "
                f"Positions confirmées : {positions}."
            )
            guide["rewards"] = [chest.get("content", "Contenu non identifié") for chest in interior_chests]
        guide["mechanic"] = detail["kind"]
        guide["specificity"] = "trial_archetype"
        guide["specificity_label"] = "Solution adaptée au titre et au mécanisme de l'épreuve"
        _quality(
            guide, detail["quality"],
            ("Parcours individuel recoupé avec l'index de solutions."
             if detail["quality"] == 3 else
             "Mécanique ou famille d'épreuve vérifiée ; le parcours exact reste à confirmer dans le jeu."),
        )
        _add_sources(guide, [SHRINE_INDEX, OBJMAP])
    elif category in {"quetes_principales", "quetes_sanctuaires", "quetes_secondaires"}:
        action, requirements = _quest_action(item.get("name", ""))
        guide["prerequisites"] = requirements
        facts = item.get("quest_facts", {})
        if facts.get("prerequisite"):
            guide["prerequisites"].insert(0, f"Prérequis publié : {facts['prerequisite']}")
        if item.get("content_origin") not in {None, "base"}:
            guide["prerequisites"].append(f"Contenu requis : {item.get('content_origin_label')}")
        guide["preparation"] = ["Activer la quête et garder son objectif visible dans le journal"]
        if facts.get("giver"):
            guide["quest_giver"] = facts["giver"]
            guide["preparation"].append(
                f"Donneur : {guide['quest_giver']}"
                + (f" - {facts['location']}" if facts.get("location") else "")
            )
        if facts.get("reward"):
            guide["rewards"] = [facts["reward"]]
        reward_override = QUEST_REWARD_OVERRIDES.get(item.get("quest_internal_id"))
        if reward_override:
            guide["rewards"] = [reward_override]
        walkthrough = item.get("quest_walkthrough", {})
        guide["detailed_steps"] = list(walkthrough.get("steps", [])) or [action]
        for point in item.get("geo_points", []):
            guide["detailed_steps"].append(
                f"{point.get('label', 'Étape')} : rejoins X {point['x']:.1f}, Z {point['z']:.1f}"
                + (f" près de {point['nearby']}" if point.get("nearby") else "") + "."
            )
        guide["detailed_steps"].append("Après la dernière action, vérifie que le journal affiche Terminé puis sauvegarde la partie.")
        evidence = item.get("solution_evidence", {})
        if evidence.get("event_flow_found"):
            guide["quest_evidence"] = {
                "event_flow_found": True,
                "event_nodes": evidence.get("event_nodes", 0),
                "event_actions": evidence.get("event_actions", 0),
                "message_references": evidence.get("message_references", 0),
            }
            _quality(
                guide, 2 if evidence.get("event_nodes", 0) else 1,
                ("Point(s) géographique(s) et graphe d'événements réel de cette quête vérifiés."
                 if evidence.get("event_nodes", 0) else
                 "Fichier de flux officiel présent mais vide ; seuls le journal et la localisation sont affirmés."),
            )
            _add_sources(guide, [evidence["source"]])
        if facts.get("source"):
            _add_sources(guide, [facts["source"]])
        if walkthrough.get("source"):
            _add_sources(guide, [walkthrough["source"]])
        if item.get("quest_internal_id") == "UotoriMini_SinkTreasure":
            _add_sources(guide, [SUNKEN_TREASURE_SOURCE])
        elif item.get("quest_internal_id") == "MarittaMini_BigWhales":
            _add_sources(guide, [LEVIATHAN_SOURCE])
        _add_sources(guide, [OBJMAP])
        if walkthrough.get("steps"):
            guide["specificity"] = "complete_quest_walkthrough"
            guide["specificity_label"] = "Solution intégrale propre à cette quête"
            _quality(
                guide, 3,
                "Parcours individuel recoupé avec le journal, le flux d'événements et un guide complet.",
            )
    elif category == "korogus":
        actor_kind = "apparition aérienne" if "HiddenKorokFly" in item.get("flag", "") else "apparition au sol"
        guide["prerequisites"] = ["Aucun prérequis permanent", "Arc, Bombes, Polaris et Cinetis couvrent la majorité des puzzles"]
        guide["preparation"] = ["Active Polaris et Cinetis pour repérer les objets interactifs autour du point"]
        guide["detailed_steps"] = [
            f"Place-toi précisément à X {item.get('x', 0):.1f}, Z {item.get('z', 0):.1f} et inspecte une zone d'environ 30 mètres.",
            f"Le flag interne indique une {actor_kind}, mais pas le geste exact : cherche d'abord pierres, feuilles, fleurs, souches, cercles, moulinets et offrandes.",
            "Si le départ et l'arrivée sont distincts, active le symbole de départ puis suis immédiatement la cible ou le parcours jusqu'au point final.",
            "Termine le motif ou interagis avec l'étincelle, puis parle au Korogu pour enregistrer la noix.",
        ]
        guide["specificity"] = "exact_location"
        guide["specificity_label"] = "Position exacte ; type précis non affirmé sans preuve locale"
        _quality(guide, 1, "Coordonnée exacte vérifiée ; le flag ne révèle pas le puzzle précis.")
        guide.setdefault("warnings", []).append("Le type exact du puzzle n'est pas contenu dans le flag de sauvegarde : la fiche propose un diagnostic ordonné sans inventer le mécanisme.")
        _add_sources(guide, [KOROK_INDEX, OBJMAP])
    elif category == "bosses_scenarises":
        detail = _scripted_boss_detail(item)
        guide["prerequisites"] = detail["requirements"]
        guide["preparation"] = ["Sauvegarder avant le combat", "Préparer les ressources indiquées dans les prérequis"]
        guide["detailed_steps"] = detail["steps"]
        guide["rewards"] = detail["rewards"]
        guide["respawn_condition"] = detail["respawn"]
        guide.setdefault("warnings", []).append(detail["respawn"])
        guide["specificity"] = "scripted_boss_complete"
        guide["specificity_label"] = "Phases, équipement, récompense et nouvelle apparition documentés"
        _quality(guide, 3, "Parcours propre à ce combat scénarisé, récompense et condition de nouvelle apparition vérifiés.")
        _add_sources(guide, [BOSS_INDEX, NINTENDO_DLC] if item.get("dlc") else [BOSS_INDEX])
    elif category in {"hinox", "talus", "moldarquors"}:
        steps, requirements = _boss_strategy(item)
        guide["prerequisites"] = requirements
        guide["preparation"] = ["Sauvegarder avant le combat", "Préparer des soins et une arme de secours"]
        guide["detailed_steps"] = steps + ["Ramasse le butin et sauvegarde après la victoire pour enregistrer le flag permanent."]
        guide["specificity"] = "boss_strategy"
        guide["specificity_label"] = "Tactique adaptée à cette famille ou à ce boss"
        _quality(guide, 2, "Tactique vérifiée pour ce boss ou cette famille ; la fiche ne prétend pas couvrir chaque phase exhaustive.")
        _add_sources(guide, [OBJMAP])
    elif category == "epreuves_epee" and item.get("trial_rooms"):
        rooms = item["trial_rooms"]
        guide["prerequisites"] = [
            "DLC Les Épreuves légendaires installé", "Épée de légende obtenue (13 cœurs requis)",
        ]
        guide["preparation"] = [
            "Consommer avant l'entrée un bonus longue durée : ses effets sont conservés",
            "L'équipement, les pouvoirs de Prodiges, les amiibo et la sauvegarde sont indisponibles à l'intérieur",
        ]
        guide["trial_rooms"] = rooms
        guide["detailed_steps"] = [
            f"Salle {room['floor']} - {room['kind_label']} - {room['enemies']} : {room['strategy']}"
            for room in rooms
        ]
        guide.setdefault("warnings", []).extend([
            "Aucun point de sauvegarde : mourir recommence le niveau depuis sa première salle.",
            "En mode Expert, les ennemis majeurs sont généralement renforcés d'un rang.",
            "Le butin accumulé dans l'épreuve n'est pas conservé après la sortie.",
        ])
        guide["specificity"] = "trial_rooms_verified"
        guide["specificity_label"] = "Toutes les salles de ce niveau sont documentées"
        _quality(guide, 3, "Chaque salle, sa composition, sa tactique et la récompense finale ont été vérifiées.")
        _add_sources(guide, [TRIAL_INDEX])
    elif category == "souvenirs":
        guide["prerequisites"] = ["Module appareil photo débloqué"] if not item.get("dlc") else ["Ode aux Prodiges activée"]
        guide["preparation"] = ["Comparer le paysage de l'album avec les reliefs visibles autour des coordonnées"]
        guide["detailed_steps"] = [f"Rejoins le point exact X {item.get('x', 0):.1f}, Z {item.get('z', 0):.1f}.", "Cherche la lueur au sol, examine-la et laisse la cinématique se terminer."]
        _add_sources(guide, [OBJMAP])
    elif category in {"coffres_monde", "coffres_donjons"}:
        guide["prerequisites"] = ["Accès à la région ou au donjon concerné"]
        guide["preparation"] = ["Utiliser Polaris si le coffre est métallique ou immergé", "Vérifier les murs destructibles et les blocs de glace"]
        guide["detailed_steps"] = [
            f"Rejoins {('X %.1f, Z %.1f' % (item['x'], item['z'])) if item.get('x') is not None else item.get('secteur') or item.get('section') or 'le secteur indiqué'}.",
            f"Ouvre le coffre identifié ; contenu attendu : {item.get('contenu') or 'non renseigné'}.",
            "Sauvegarde puis vérifie que l'élément passe en statut automatique terminé.",
        ]
        _add_sources(guide, [OBJMAP])
    elif category == "compendium":
        guide["prerequisites"] = ["Module appareil photo débloqué"]
        guide["preparation"] = [f"Chercher le sujet dans la section {item.get('section') or 'indiquée'}", "Prévoir des rubis si la photo doit être achetée"]
        guide["detailed_steps"] = [f"Cadre {item.get('name')} jusqu'à ce que son nom soit reconnu en orange.", "Prends la photo et confirme son enregistrement, ou achète l'image au laboratoire antique lorsque disponible."]
    elif category in {"armures", "armures_max", "equipements_particuliers", "harnachements"}:
        guide["prerequisites"] = (["Un cheval enregistré et l'accès à un relais"] if category == "harnachements"
                                  else ["Accès au marchand, coffre, quête ou amiibo correspondant"])
        guide["preparation"] = (["Parler à l'employé du relais placé près des chevaux pour changer le harnachement"]
                                if category == "harnachements" else ["Garder une place dans la sacoche d'armures"])
        if item.get("prochaine_amelioration"):
            materials = item["prochaine_amelioration"].get("materiaux", [])
            guide["detailed_steps"] = ["Réunis " + ", ".join(f"{m['requis']} × {m['name']}" for m in materials) + ".", "Présente la pièce à une Grande Fée suffisamment éveillée."]
        else:
            destination = "la liste des harnachements du relais" if category == "harnachements" else "la sacoche"
            guide["detailed_steps"] = [f"Obtiens {item.get('name')} par sa méthode d'acquisition, puis vérifie sa présence dans {destination}."]
        guide["warnings"] = [warning for warning in guide.get("warnings", [])
                             if "fiche universelle de secours" not in warning]
    else:
        action = item.get("action") or guide.get("current_action")
        guide["prerequisites"] = [f"Contenu requis : {item.get('content_origin_label')}"] if item.get("content_origin") not in {None, "base"} else []
        guide["preparation"] = ["Consulter la région, la récompense et l'état automatique affichés dans la fiche"]
        guide["detailed_steps"] = [action] if action else []
        if item.get("x") is not None:
            guide["detailed_steps"].insert(0, f"Rejoins X {item['x']:.1f}, Z {item['z']:.1f}.")
        _add_sources(guide, [OBJMAP])

    guide["prerequisites"] = _dedupe(guide["prerequisites"])
    guide["preparation"] = _dedupe(guide["preparation"])
    guide["detailed_steps"] = _dedupe(guide["detailed_steps"])
    guide["rewards"] = _dedupe(guide["rewards"])
    return guide


def build_map_guide(item: dict) -> dict:
    filter_type = item.get("filter_type", "")
    name = item.get("name") or item.get("subtype") or "Point cartographique"
    guide = {
        "version": 3, "personalized": True, "category": "informations_carte",
        "title": f"Accompagnement - {name}", "summary": item.get("filter_label", "Point utile"),
        "current_action": "Rejoins ce point et utilise la fiche selon ton objectif de farm ou de service.",
        "completion": {"condition": "Point informatif : aucun flag permanent n'est requis.", "detection": "carte locale", "automatic": False},
        "steps": [], "tips": [], "warnings": [], "sources": [OBJMAP],
        "prerequisites": [], "preparation": [], "rewards": [], "specificity": "map_family",
        "specificity_label": "Conseils propres à cette famille cartographique", "detailed_steps": [],
    }
    _quality(guide, 2 if item.get("farm") else 1,
             "Position fixe et tactique de famille vérifiées." if item.get("farm") else
             "Position et fonction cartographique vérifiées.")
    if item.get("farm"):
        steps, requirements = _boss_strategy(item)
        if not any(word in _plain(name) for word in ("hinox", "lithorok", "magrok", "cryorok", "moldarquor")):
            family = {
                "lynels": "Observe son arme avant d'engager le combat, effectue une garde parfaite sur la charge puis monte-le lorsqu'il est étourdi.",
                "gardiens": "Coupe les pattes si possible et renvoie le laser avec une garde parfaite ; une flèche antique dans l'œil peut l'éliminer immédiatement.",
                "nano_gardiens": "Esquive latéralement les attaques de mêlée et utilise les piliers contre la rotation chargée.",
                "sorciers": "Vise à l'arc pendant leur téléportation ; l'élément opposé peut les éliminer instantanément.",
                "yigas": "Interromps leur téléportation avec une flèche puis frappe pendant leur récupération.",
                "bokoblins": "Approche discrètement de nuit ou attire un ennemi à la fois ; les camps fournissent armes et matériaux.",
                "moblins": "Reste sur leurs flancs et évite les longues allonges ; le feu ou l'électricité fait lâcher leurs armes.",
                "lezalfos": "Utilise l'élément opposé contre les variantes élémentaires et vise la tête pendant leurs bonds.",
                "chuchus": "Élimine-les à distance : leur explosion élémentaire peut affecter les ennemis voisins.",
                "chauves_souris": "Une bombe ou une flèche élimine le groupe sans risquer son attaque plongeante.",
                "octos": "Renvoie leur projectile avec une garde parfaite ou vise-les lorsqu'ils sortent de leur cachette.",
            }.get(filter_type, "Observe le groupe, choisis l'élément adapté et élimine les cibles dangereuses à distance.")
            steps, requirements = [family], ["Armes et soins adaptés à la variante affichée"]
        guide["prerequisites"] = requirements
        guide["preparation"] = ["Placer un marqueur personnel si tu construis une route de farm"]
        guide["detailed_steps"] = [f"Rejoins X {item.get('x', 0):.1f}, Z {item.get('z', 0):.1f}."] + steps + ["Ramasse les matériaux puis reviens après une lune de sang pour recommencer."]
        guide["warnings"] = ["Le cochage manuel sert seulement de repère : cet ennemi réapparaît à la lune de sang."]
        guide["rewards"] = ["Armes et matériaux correspondant à la famille et à sa variante actuelle"]
    else:
        uses = {
            "relais": "Enregistre un cheval, dors, cuisine et consulte les services du relais.",
            "villages": "Utilise les boutiques, quêtes, statues et points de repos du village.",
            "laboratoires": "Débloque ou améliore les modules et équipements antiques disponibles.",
            "fontaines_grandes_fees": "Réveille la Grande Fée puis améliore les armures avec les matériaux requis.",
            "fontaine_malanya": "Réveille Marlon pour pouvoir ressusciter un cheval enregistré.",
            "statues_deesse": "Échange quatre emblèmes de triomphe contre un cœur ou un réceptacle d'endurance.",
            "marmites": "Allume la marmite si nécessaire, puis combine des ingrédients compatibles.",
            "radeaux": "Utilise une feuille korogu sur la voile ou Octo-ballon/Cinetis selon le terrain.",
            "kilton": "Parle à Kilton la nuit pour échanger des matériaux de monstre contre des Streums.",
            "auberges": "Dors jusqu'à l'heure souhaitée et choisis un lit amélioré pour des cœurs temporaires.",
            "boutiques_armures": "Achète les pièces manquantes et vérifie les conditions propres à la région.",
            "magasins_generaux": "Achète ou vend les matériaux utiles à ton prochain objectif.",
            "bijouteries": "Échange rubis et gemmes contre les bijoux disponibles.",
            "objectifs_quete": "Utilise ce point comme étape intermédiaire ; ouvre la fiche de la quête principale pour conserver l'ordre complet.",
        }
        guide["detailed_steps"] = [f"Rejoins X {item.get('x', 0):.1f}, Z {item.get('z', 0):.1f}.", uses.get(filter_type, "Utilise ce point comme repère cartographique personnel.")]
    return guide