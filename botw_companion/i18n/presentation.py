from functools import lru_cache
from importlib.resources import files
import json
import re
from . import message, resolve, default_locale, locale_info, settings, immutable

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
    'selected_source', 'engine_name', 'device_name', 'controller_name', 'language',
})
TECHNICAL_VALUE = re.compile(r'(?:[a-z][a-z0-9_]*:[A-Za-z0-9_:.-]+|[a-z][a-z0-9]*_[a-z0-9_]+)\Z')


# Legacy reports carry source text rather than message IDs. Keep their display
# translation separate from personal data and protocol values.
class Presenter:
    def __init__(self, locale, reference=None, format_message=None):
        self.locale = locale
        if reference is None:
            root = files('botw_companion').joinpath('locales', locale)
            reference = json.loads(root.joinpath('presentation-data.json').read_text(encoding='utf-8'))
        self.reference = immutable(reference)
        self.format_message = format_message or message

    @lru_cache(maxsize=16)
    def _compound_rules(self):
        terms = {**self.reference['glossary'], **self.reference['strings']}
        terms = {k.strip(): v.strip() for k, v in terms.items()
                 if len(k.strip()) >= 4 and 'ZXQ' not in k and '\n' not in k}
        # Keep already-localized names intact when source aliases overlap.
        for value in list(terms.values()):
            terms.setdefault(value, value)
        pattern = re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(k) for k in sorted(terms, key=len, reverse=True)) + r')(?!\w)')
        return pattern, terms


    @lru_cache(maxsize=16)
    def _dynamic_rules(self):
        rules = []
        for entry in self.reference['patterns']:
            source = entry['source']
            chunks = re.split(r'(ZXQ\d+QXZ)', source)
            numeric = frozenset(str(index) for index in entry.get('numeric_values', []))
            regex = ''.join('(?P<v' + c[3:-3] + '>' +
                            (r'[-+]?\d+(?:\.\d+)?' if c[3:-3] in numeric else '.*?') + ')'
                            if re.fullmatch(r'ZXQ\d+QXZ', c) else re.escape(c) for c in chunks)
            literals = [c for c in chunks if c and not re.fullmatch(r'ZXQ\d+QXZ', c)]
            rules.append((re.compile(regex, re.S), entry['message'], literals,
                          frozenset(str(index) for index in entry.get('preserve_values', [])), numeric))
        return rules


    @lru_cache(maxsize=32768)
    def translate_text(self, value: str) -> str:
        # Dynamic diagnostics may contain user paths or URLs. Translating a game
        # name inside one would change the resource that the message identifies.
        if re.match(r'^(?:[A-Za-z]:[\\/]|/|~[\\/]|\\\\|https?://)', value):
            return value
        strings = self.reference['strings']
        compiled = self.reference.get('compiled_strings', {})
        if value in strings:
            return strings[value]
        if value in compiled:
            return compiled[value]
        if TECHNICAL_VALUE.fullmatch(value):
            return value
        binding = self.reference.get('exact_messages', {}).get(value)
        if binding:
            return self.format_message(binding['message'], self.locale, **binding['values'])
        stripped = value.strip()
        if stripped in strings:
            return value[:len(value) - len(value.lstrip())] + strings[stripped] + value[len(value.rstrip()):]
        for pattern, target, literals, preserve, numeric in self._dynamic_rules():
            if any(literal not in value for literal in literals):
                continue
            match = pattern.fullmatch(value)
            if match:
                values = {}
                for key, captured in match.groupdict().items():
                    index = key[1:]
                    values['value' + index] = (captured if index in preserve or captured == value
                                               else self.translate_text(captured))
                    if index in numeric:
                        values['number' + index] = float(captured)
                return self.format_message(target, self.locale, **values)
        pattern, terms = self._compound_rules()
        return pattern.sub(lambda m: terms[m[0]], value)


    def present(self, value, field: str = ''):
        """Return a translated copy; identifiers, coordinates and notes stay stable."""
        if field == 'controllers' and isinstance(value, list):
            # Device names are external values, even when they coincide with a
            # game term. Only the application's missing-name label is prose.
            return [{**controller, 'name': self.translate_text(controller['name'])}
                    if isinstance(controller, dict) and controller.get('name') == 'Contrôleur inconnu'
                    else controller for controller in value]
        if field in TECHNICAL_FIELDS or field.endswith(('_flag', '_path', '_id', '_url', '_sha256')):
            return value
        if field == 'strategy' and isinstance(value, str) and value in {'distance', 'region', 'manual'}:
            return value
        if isinstance(value, str) and TECHNICAL_VALUE.fullmatch(value):
            return value
        if isinstance(value, dict):
            result = {key: self.present(child, key) for key, child in value.items()}
            def align_term(child, previous, official, child_field=''):
                if child_field in TECHNICAL_FIELDS or child_field.endswith(('_flag', '_path', '_id', '_url', '_sha256')):
                    return child
                if isinstance(child, str):
                    return re.sub(re.escape(previous) + r'(?!\+)', lambda _: official, child)
                if isinstance(child, list):
                    return [align_term(x, previous, official, child_field) for x in child]
                if isinstance(child, dict):
                    return {k: align_term(x, previous, official, k) for k, x in child.items()}
                return child
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
                names = self.reference['names_by_id']
                official = names.get(category + ':' + str(identity))
                if not official:
                    official = names.get('compendium:' + str(identity)) or names.get('armor_owned:' + str(identity))
                if official:
                    previous = result['name']
                    result['name'] = official
                    if previous != official:
                        if 'guide' in result:
                            result['guide'] = align_term(result['guide'], previous, official)
            # DLC Ruvo Korbah legitimately has a '+' trial title. Resolve the title
            # by dungeon identity rather than globally rewriting a shared French
            # alias used by both ordinary and DLC Major Tests of Strength.
            if identity and isinstance(value.get('trial'), str):
                official_trial = self.reference.get('trials_by_id', {}).get(str(identity))
                previous_trial = result['trial']
                if official_trial and previous_trial != official_trial:
                    result = align_term(result, previous_trial, official_trial)
                    result['trial'] = official_trial
            return result
        if isinstance(value, list):
            return [self.present(child, field) for child in value]
        return self.translate_text(value) if isinstance(value, str) else value

@lru_cache(maxsize=16)
def presenter(locale, revision=None):
    return Presenter(locale)


def translate_text(value, locale=None):
    locale = resolve(locale) or default_locale()
    if locale == settings()['source_locale']:
        return value
    return presenter(locale, locale_info(locale)['revision']).translate_text(value)


def present(value, locale=None, field=''):
    locale = resolve(locale) or default_locale()
    if locale == settings()['source_locale']:
        return value
    return presenter(locale, locale_info(locale)['revision']).present(value, field)
