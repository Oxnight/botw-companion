"""Regression tests for game terminology and conditional API prose."""
import copy
import json
from pathlib import Path
import re
import tempfile
import unittest

from botw_companion.analyzer import analyze
from botw_companion.dsu.manager import DsuManager
from botw_companion.english import english_presentation, translate_text, TECHNICAL_FIELDS
from botw_companion.platforms import platform_metadata
from botw_companion.quest_walkthroughs import QUEST_WALKTHROUGHS
from botw_companion.resources import load_catalog
import test_analyzer as analyzer_fixture
from tools.localization_checks import has_french_prose, has_bad_english

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {'shrines': 'sanctuaires', 'shrine_chests': 'coffres_sanctuaires',
              'compendium': 'compendium', 'armor_owned': 'armures',
              'special_armor': 'equipements_particuliers', 'main_quests': 'quetes_principales',
              'shrine_quests': 'quetes_sanctuaires', 'side_quests': 'quetes_secondaires'}


def prose_failures(value, field='', path=''):
    """Ignore protocol identifiers and personal data, including descendants."""
    if field in TECHNICAL_FIELDS or field.endswith(('_flag', '_path', '_id', '_url', '_sha256')):
        return []
    if isinstance(value, dict):
        return [failure for k, child in value.items()
                for failure in prose_failures(child, k, path + '/' + k)]
    if isinstance(value, list):
        return [failure for i, child in enumerate(value)
                for failure in prose_failures(child, field, path + '/' + str(i))]
    if isinstance(value, str):
        if re.fullmatch(r'(?:[a-z][a-z0-9_]*:[A-Za-z0-9_:.-]+|[a-z][a-z0-9]*_[a-z0-9_]+)', value):
            return []
        if has_french_prose(value) or has_bad_english(value):
            return [(path, value)]
    return []


class TranslationRegressionTests(unittest.TestCase):
    def test_nintendo_expansion_terms_accept_both_apostrophe_forms(self):
        # Publisher references, independently of the application dictionary:
        # https://www.nintendo.com/fr-fr/Jeux/Jeux-Nintendo-Switch/The-Legend-of-Zelda-Breath-of-the-Wild-1173609.html
        # https://www.nintendo.com/us/store/products/the-legend-of-zelda-breath-of-the-wild-expansion-pass-70070000000041-switch/
        terms = {
            "Épreuves de l'épée": 'Trial of the Sword',
            "Épreuves de l’épée": 'Trial of the Sword',
            "L'Ode aux Prodiges": "The Champions' Ballad",
            "L’Ode aux Prodiges": "The Champions' Ballad",
            'Tétralame Mort-Subite': 'One-Hit Obliterator',
            'Tétralame mort-subite': 'One-Hit Obliterator',
            'Amulette de téléportation': 'Travel Medallion',
            'Destrier de légende 0.1': 'Master Cycle Zero',
            'Masque de Korogu': 'Korok Mask',
            'Asarim': 'Kass',
            'Plateau du Prélude': 'Great Plateau',
            'Mode expert': 'Master Mode',
        }
        for french, expected in terms.items():
            with self.subTest(term=french):
                self.assertEqual(translate_text(french), expected)
        self.assertEqual(translate_text('Ode aux Prodiges activée'),
                         "The Champions' Ballad quest started")

    @classmethod
    def setUpClass(cls):
        cls.french = analyze({})
        cls.english = english_presentation(cls.french)

    def test_official_names_and_all_shrine_trials_by_identifier(self):
        reference = json.loads((ROOT/'tests/fixtures/official_english_names.json').read_text())
        lookup = {group: {item['id']: item for item in self.english['categories'][category]['elements']}
                  for group, category in CATEGORIES.items()}
        for row in reference['names']:
            with self.subTest(group=row['group'], id=row['id']):
                self.assertEqual(lookup[row['group']][row['id']]['name'], row['expected'])
        for row in reference['trials']:
            with self.subTest(trial=row['id']):
                self.assertEqual(lookup['shrines'][row['id']]['trial'], row['expected'])
        ri_dahi = next(item for item in self.french['categories']['sanctuaires']['elements']
                       if item['id'] == 'Dungeon047')
        self.assertEqual(ri_dahi['trial'], 'Question de timing')

    def test_all_progression_states_have_translated_prose(self):
        catalog = load_catalog()
        started = {rule['flag']: rule.get('value', True)
                   for group in ('main_quests', 'side_quests', 'shrine_quests')
                   for item in catalog[group] for rule in item.get('started_rule', [])}
        flags, inventory = analyzer_fixture.AnalyzerTests._complete_profile_fixture(
            {'base', 'master_trials', 'champions_ballad', 'amiibo'})
        partial = [{'id': item['variants'][1], 'quantite': 1}
                   for item in catalog['armor_owned'] if len(item.get('variants', [])) > 1]
        cases = [('empty', self.french), ('started', analyze(started)),
                 ('complete', analyze(flags, inventory)),
                 ('expert', analyze({}, save_context={'mode': 'expert', 'is_expert': True})),
                 ('partial-armor', analyze({}, partial))]
        for name, report in cases:
            with self.subTest(scenario=name):
                translated = english_presentation(report)
                self.assertEqual(prose_failures(translated), [])
        for level in range(1, 5):
            source = f'Amélioration {level} étoile{"s" if level > 1 else ""} - Présente la pièce et les matériaux requis à une Grande Fée débloquée.'
            self.assertEqual(translate_text(source), f'{level}-star upgrade - Bring the armor piece and required materials to an unlocked Great Fairy.')

    def test_dsu_diagnostics_and_platform_relaunch_hints(self):
        healthy = {'calibration_valid': True, 'health': 'ok', 'received_hz': 200,
                   'sent_hz': 200, 'sample_age_ms': 5, 'measurement_age_seconds': 1}
        cases = [('off', None), ('starting', None), ('ready', {'calibration_valid': False}),
                 ('waiting_controller', {'calibration_valid': True}),
                 ('ready', healthy), ('ready', {**healthy, 'received_hz': 150}),
                 ('ready', {**healthy, 'received_hz': 0})]
        expected = ['inactive', 'collecting', 'recalibration', 'collecting', 'excellent', 'correct', 'unstable']
        for (state, telemetry), diagnostic_status in zip(cases, expected):
            diagnostic = DsuManager._diagnostic(state, state != 'off', telemetry)
            translated = english_presentation(diagnostic)
            self.assertEqual(translated['status'], diagnostic_status)
            self.assertEqual(prose_failures(translated), [])
        with tempfile.TemporaryDirectory() as tmp:
            for system in ['Darwin', 'Windows', 'Linux', 'Other']:
                original = platform_metadata(system, home=Path(tmp), environ={})
                frozen = copy.deepcopy(original)
                translated = english_presentation(original)
                self.assertTrue(translated['relaunch_hint'].startswith('You can close this tab.'))
                self.assertEqual(prose_failures(translated), [])
                self.assertEqual(original, frozen)
                manager = DsuManager(system=system, executable=Path(tmp)/'missing-engine',
                                     launcher=Path(tmp)/'missing-launcher',
                                     sdl_library=Path(tmp)/'missing-SDL', support_dir=Path(tmp), probe=lambda: None)
                self.assertEqual(prose_failures(english_presentation(manager.status())), [])

    def test_dynamic_controller_names_and_errors_are_not_rewritten(self):
        name = 'Manette Cocorico — Arbre Mojo'
        message = f'« {name} » n’expose pas un gyroscope et un accéléromètre compatibles.'
        self.assertEqual(translate_text(message), f'“{name}” does not expose a compatible gyroscope and accelerometer.')
        error = '/tmp/Cocorico/Épée de feu: access denied'
        self.assertEqual(translate_text('Démarrage impossible : ' + error), 'Unable to start: ' + error)

    def test_quest_instructions_and_hidden_trial_room_summaries(self):
        quest = QUEST_WALKTHROUGHS['HatenoMini_WeaponMania']
        english = english_presentation(quest)
        self.assertIn('Nebb', english['steps'][0])
        ordered = ["Traveler's Sword", 'Fire Rod', 'Moblin Club', 'Duplex Bow', 'Windcleaver',
                   'Ancient Battle Axe+', 'Frostspear', 'Ancient Short Sword']
        positions = [english['steps'][1].index(name) for name in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('Ancient Short Sword', english['steps'][2])
        darners = english_presentation(QUEST_WALKTHROUGHS['MinakkareMini_Dragonfly'])
        for term in ('Electric Darner', 'Cold Darner', 'Warm Darner'):
            self.assertIn(term, darners['steps'][1])
        self.assertIn('Gleema', darners['steps'][2])
        self.assertEqual(translate_text('Journal EX de Lambda 2'), "Misko's EX Journal 2")
        self.assertEqual(translate_text('Pomme au miel enduro'), 'Honeyed Apple')
        for volume, stable in enumerate(('Woodland Stable', 'South Akkala Stable',
                                         'Highland Stable', 'Riverside Stable'), 1):
            instruction = QUEST_WALKTHROUGHS[f'TreasureHunt0{volume}']['steps'][0]
            self.assertEqual(translate_text(instruction),
                             f'Read Super Rumor Mill EX: Volume {volume} at {stable}.')
        self.assertNotIn('gueule de bois', str(QUEST_WALKTHROUGHS['ShieldofKolog']))
        self.assertEqual(prose_failures(english_presentation(QUEST_WALKTHROUGHS)), [])
        summaries = []
        def visit(v, field=''):
            if isinstance(v, dict):
                for k, child in v.items(): visit(child, k)
            elif isinstance(v, list):
                for child in v: visit(child, field)
            elif field == 'detailed_steps' and isinstance(v, str) and v.startswith('Room '):
                summaries.append(v)
        visit(self.english)
        self.assertGreaterEqual(len(set(summaries)), 54)
        self.assertEqual(prose_failures(summaries), [])

    def test_official_accented_english_is_allowed_but_french_is_rejected(self):
        self.assertFalse(has_french_prose('Bring Salmon Meunière and Sautéed Nuts.'))
        self.assertTrue(has_french_prose('Bring Salmon Meunière puis retourne au village Piaf.'))


if __name__ == '__main__':
    unittest.main()
