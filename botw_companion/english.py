"""Offline English presentation, isolated from save data and protocol values."""
from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
import json
import re

TECHNICAL_FIELDS = frozenset({
    'id', 'hash', 'flag', 'actor', 'acteur', 'quest_internal_id', 'any_flags',
    'usage_flags', 'category', 'categorie', 'type', 'kind', 'status', 'state',
    'mode', 'content_origin', 'feature', 'source_url', 'url', 'endpoint', 'path',
    'chemin', 'directory', 'filename', 'file', 'log_path', 'session_token',
    'report_revision_key', 'fingerprint', 'technical_name', 'note_personnelle',
    'game_mode_scope', 'display_scope', 'location_status', 'tracking_mode',
    'quality', 'shutdown_reason', 'profile_id', 'layer_type', 'filter_type',
    'role', 'scope', 'save_mode', 'default_mode_filter', 'placement_kinds',
    'coverage_scopes', 'included_categories', 'missing_categories',
})


@lru_cache(maxsize=1)
def reference() -> dict:
    root = files('botw_companion.data')
    data = json.loads(root.joinpath('localization_en.json').read_text(encoding='utf-8'))
    curated = json.loads(root.joinpath('localization_en_ui.json').read_text(encoding='utf-8'))
    data['strings'].update(curated['strings'])
    data['glossary'].update({k: v for k, v in curated['strings'].items() if len(k) >= 4})
    return data


@lru_cache(maxsize=1)
def _compound_rules():
    terms = {**reference()['glossary'], **reference()['strings']}
    terms = {k.strip(): v.strip() for k, v in terms.items()
             if len(k.strip()) >= 4 and 'ZXQ' not in k and '\n' not in k}
    # Keep already-English names intact when French aliases share substrings.
    for value in list(terms.values()):
        terms.setdefault(value, value)
    pattern = re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(k) for k in sorted(terms, key=len, reverse=True)) + r')(?!\w)')
    return pattern, terms


@lru_cache(maxsize=1)
def _dynamic_rules():
    rules = []
    for entry in reference()['patterns']:
        source = entry['source']
        chunks = re.split(r'(ZXQ\d+QXZ)', source)
        regex = ''.join('(?P<v' + c[3:-3] + '>.*?)' if re.fullmatch(r'ZXQ\d+QXZ', c) else re.escape(c) for c in chunks)
        literals = [c for c in chunks if c and not re.fullmatch(r'ZXQ\d+QXZ', c)]
        rules.append((re.compile(regex, re.S), entry['target'], literals))
    return rules


@lru_cache(maxsize=32768)
def translate_text(value: str) -> str:
    # Dynamic diagnostics may contain user paths or URLs. Translating a game
    # name inside one would change the resource that the message identifies.
    if re.match(r'^(?:[A-Za-z]:[\\/]|/|~[\\/]|\\\\|https?://)', value):
        return value
    strings = reference()['strings']
    compiled = reference().get('compiled_strings', {})
    if value in strings:
        return strings[value]
    if value in compiled:
        return compiled[value]
    stripped = value.strip()
    if stripped in strings:
        return value[:len(value) - len(value.lstrip())] + strings[stripped] + value[len(value.rstrip()):]
    for pattern, target, literals in _dynamic_rules():
        if any(literal not in value for literal in literals):
            continue
        match = pattern.fullmatch(value)
        if match:
            return re.sub(r'ZXQ(\d+)QXZ', lambda m: translate_text(match.group('v' + m[1]))
                          if match.group('v' + m[1]) != value else value, target)
    pattern, terms = _compound_rules()
    return pattern.sub(lambda m: terms[m[0]], value)


def english_presentation(value, field: str = ''):
    """Return a translated copy; identifiers, coordinates and notes stay stable."""
    if field in TECHNICAL_FIELDS or field.endswith(('_flag', '_path', '_id', '_url', '_sha256')):
        return value
    if field == 'strategy' and isinstance(value, str) and value in {'distance', 'region', 'manual'}:
        return value
    if isinstance(value, str) and re.fullmatch(
        r'(?:[a-z][a-z0-9_]*:[A-Za-z0-9_:.-]+|[a-z][a-z0-9]*_[a-z0-9_]+)', value
    ):
        return value
    if isinstance(value, dict):
        result = {key: english_presentation(child, key) for key, child in value.items()}
        identity = value.get('id')
        if identity and isinstance(value.get('name'), str):
            category = value.get('categorie') or value.get('category') or ''
            aliases = {'sanctuaires': 'shrines', 'coffres_sanctuaires': 'shrine_chests',
                       'armures': 'armor_owned', 'armures_max': 'armor_owned',
                       'equipements_particuliers': 'special_armor', 'souvenirs': 'memories',
                       'creatures_divines': 'divine_beasts',
                       'bosses_scenarises': 'scripted_bosses', 'bonus_expansion': 'expansion_bonus_chests',
                       'objets_speciaux': 'special_items',
                       'harnachements': 'horse_gear', 'recompenses_uniques': 'unique_rewards', 'quetes_principales': 'main_quests',
                       'quetes_secondaires': 'side_quests', 'quetes_sanctuaires': 'shrine_quests'}
            category = aliases.get(category, category)
            names = reference()['names_by_id']
            official = names.get(category + ':' + str(identity))
            if not official:
                official = names.get('compendium:' + str(identity)) or names.get('armor_owned:' + str(identity))
            if official:
                previous = result['name']
                result['name'] = official
                if previous != official:
                    def align(child):
                        if isinstance(child, str): return child.replace(previous, official)
                        if isinstance(child, list): return [align(x) for x in child]
                        if isinstance(child, dict): return {k: align(x) for k, x in child.items()}
                        return child
                    if 'guide' in result: result['guide'] = align(result['guide'])
        return result
    if isinstance(value, list):
        return [english_presentation(child, field) for child in value]
    return translate_text(value) if isinstance(value, str) else value
