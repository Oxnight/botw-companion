"""Shared language checks, allowing accented official English game names."""
import re

OFFICIAL_ACCENTED_ENGLISH = ('Salmon Meunière', 'Sautéed Nuts')

FRENCH_PROSE = re.compile(
    r'[éèêàùçœ]|\b(?:Carte|Personnel|Filtres|Zoomer|Coffre|coffre|coffres|'
    r'Sanctuaire|sanctuaire|sanctuaires|Korogus|Marlon|Elimith|Cocorico|Lithorok|'
    r'Moldarquor|Rejoins|rejoins|Donneur|Sauvegarde|sauvegarde|Selle|Filet|Ballade|'
    r'Objectif|PROCHAINE|Marquer|Ouvrir|Cinetis|Marmite|Radeau|Bijouterie|Tetralame|'
    r'référencé|terminé|ajoutée|affichée|positionné|Salle|Roi|Piaf|Mesure|Instable|'
    r'Lis|Relais|relais|introuvable|invalide|Impossible|Aucun|aucun|uniquement|fichier|Dossier|dossier)\b'
)
WRONG_ENGLISH = re.compile(
    r'\b(?:bequests|cryonics|korogu|archeonic|Receptacle of Heart|Anger of Urbosa|'
    r'Rage of Revali|Lightning Shadow|Zora Estate|Jita|Jitah|Ice Squirrel Lizalfos|'
    r'Deteriorated guards|Teleportation Medallion|Mojo Tree|Prelude Plateau|Prelude Tower|'
    r'Uzmi Peninsula|Dracos River|milling salmon|hangover trees|Flamebreaker monuments|'
    r'Flamebreaker Slate|permanent cores|Contact details of the world|global safe flag|'
    r'Lambda|tempo carrot|tempo mushrooms|frogs tempo|enduro dragonfly|glagla dragonfly|'
    r'chili dragonfly|Guardian Scout [1-4]\.0|Fire Bats|Electric bats|Stone Junior Fire Taluses|'
    r'Stone Junior Ice Taluses|Lizalfos Fire Spit|Octos|Sous-fifre Yiga)\b|'
    r'first identifies|then burns|then moves|then shows|then holds|then hits'
)


def has_french_prose(value: str) -> bool:
    for term in OFFICIAL_ACCENTED_ENGLISH:
        value = value.replace(term, '')
    return bool(FRENCH_PROSE.search(value))


def has_bad_english(value: str) -> bool:
    return bool(WRONG_ENGLISH.search(value))
