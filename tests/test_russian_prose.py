from pathlib import Path
import re
import unittest

from fluent.runtime import FluentBundle, FluentResource

from botw_companion.analyzer import analyze
from botw_companion.i18n.presentation import Presenter, present
from tools.i18n import read

ROOT = Path(__file__).resolve().parents[1]


class RussianProseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = ROOT / 'botw_companion/locales/ru'
        cls.prose = read(folder / 'prose.json')['strings']
        cls.source = read(folder.parent / 'fr/prose.json')['strings']
        cls.english = read(folder.parent / 'en/prose.json')['strings']
        cls.review = read(ROOT / 'docs/RUSSIAN_PROSE_REVIEW.json')
        cls.bundle = FluentBundle(['ru-RU'], use_isolating=False)
        cls.bundle.add_resource(FluentResource((folder / 'messages.ftl').read_text(encoding='utf-8')))
        shared = ROOT / 'botw_companion/i18n'

        def render(identity, _locale, **values):
            result, errors = cls.bundle.format_pattern(cls.bundle.get_message(identity).value, values)
            if errors:
                raise AssertionError((identity, errors))
            return result

        cls.presenter = Presenter('ru', reference={
            'strings': cls.prose, 'glossary': {},
            'patterns': read(shared / 'legacy-patterns.json'),
            'exact_messages': read(shared / 'message-bindings.json'),
            **read(folder / 'game.json'),
        }, format_message=render)
        report = analyze({})
        cls.items = {item['tracking_id']: item for section in ('elements', 'map_layers')
                     for item in report[section]}

    def rendered_item(self, identity, locale):
        item = self.items[identity]
        rendered = self.presenter.present(item) if locale == 'ru' else present(item, locale)
        self.assertEqual(rendered['tracking_id'], identity)
        return rendered

    def test_review_covers_each_canonical_key_and_matches_supplied_values(self):
        records = self.review['mappings']
        indexed = {record['key']: record for record in records}
        self.assertEqual(len(indexed), len(records))
        self.assertEqual(indexed.keys(), self.source.keys())
        self.assertEqual(self.prose.keys(), self.source.keys())
        self.assertEqual(self.review['translated'], len(self.prose))
        self.assertEqual(self.review['required'], len(self.source))
        self.assertEqual(self.review['pending'], 0)
        for key, record in indexed.items():
            with self.subTest(key=key):
                self.assertEqual(record['russian'], self.prose[key])
                self.assertEqual(record['english'], self.english[key])
                self.assertTrue(record['references'])

    def test_template_values_survive_except_documented_french_suffixes(self):
        for record in self.review['mappings']:
            source = set(re.findall(r'ZXQ(\d+)QXZ', record['key']))
            if not source:
                continue
            translated = set(re.findall(r'ZXQ(\d+)QXZ', record['russian']))
            omitted = {str(index) for index in record.get('omitted_french_suffix_slots', [])}
            with self.subTest(key=record['key']):
                self.assertLessEqual(translated, source)
                self.assertEqual(source - translated, omitted)
                if omitted:
                    self.assertIn('French plural/gender suffix slots', record['note'])

    def test_place_names_and_contextual_labels_form_complete_phrases(self):
        for key, expected in [
            ('Bazar Assek', 'Рынок «Кара-Кара»'),
            ('bazar Assek', 'Рынок «Кара-Кара»'),
            ('Maritta Vieille place des commerces', 'Рынок «Тихий»'),
            ('Vérification toutes les', 'Проверять каждые'),
            ('Vérifier toutes les', 'Проверять каждые'),
            ('Armure zora obtenue', 'Доспехи зора получены'),
            ('Prérequis publié : Armure zora obtenue', 'Указанное предварительное условие: Доспехи зора получены'),
            ('L’accès dépend de la quête «', 'Доступ зависит от задания «'),
        ]:
            with self.subTest(key=key):
                self.assertEqual(self.presenter.translate_text(key), expected)

    def test_corrected_walkthroughs_render_in_all_three_languages(self):
        cases = {
            'quetes_secondaires:rushroomrush': (2, (
                ('55 champis tempo', 'coffre derrière le relais'),
                ('55 Rushrooms', 'chest behind the stable'),
                ('55 прытковиков', 'сундук за конюшней'))),
            'quetes_secondaires:slatedforupgrades': (1, (
                ('vis antiques pour le détecteur', 'axes antiques pour Bombes', 'cœurs antiques pour Cinetis'),
                ('Screws for Sheikah Sensor', 'Shafts for Remote Bomb', 'Cores for Stasis'),
                ('винта для Датчика', 'вала для бомб', 'ядра для Стазиса'))),
            'quetes_sanctuaires:thespringofwisdom': (2, (('son écaille',), ('Naydra’s Scale',), ('чешую',))),
            'quetes_secondaires:agiftfromthemonks': (1, (("Rona'Kahta",), ('Rona Kachta Shrine',), ('Рона-Кахта',))),
            'quetes_sanctuaires:alandscapeofastable': (2, (("Ta'Mur",), ('Tah Muhl Shrine',), ('Та-Мул',))),
            'quetes_secondaires:sunkentreasure': (1, (('en radeau', 'Polaris'), ('on a raft', 'Magnesis'), ('на плоту', 'Магнезисом'))),
            'quetes_secondaires:riddlesofhyrule': (1, (('champi piment',), ('Sunshroom',), ('жаромор',))),
        }
        for identity, (index, cases_by_locale) in cases.items():
            for locale, expected in zip(('fr', 'en', 'ru'), cases_by_locale):
                with self.subTest(identity=identity, locale=locale):
                    guide = self.rendered_item(identity, locale)['guide']
                    for text in expected:
                        self.assertIn(text, guide['detailed_steps'][index])
                        self.assertTrue(any(text in step['instruction'] for step in guide['steps']))

    def test_report_labels_are_translated_without_changing_coordinates_or_ids(self):
        for locale, bow, space, step, sector, enemy in [
            ('en', 'Bow', '3D position: ', 'Solution 1/3', 'Explore sector A-1.', '4 Stalkoblins'),
            ('ru', 'Лук', 'Координаты: ', 'Решение 1/3', 'Исследуйте сектор A-1.', '4 сталкоблина'),
        ]:
            with self.subTest(locale=locale):
                shrine = self.rendered_item('sanctuaires:Dungeon001', locale)
                self.assertIn(bow, shrine['guide']['prerequisites'])
                identity = 'korogus:MainField_Npc_HiddenKorokGround_3077381654'
                korok = self.rendered_item(identity, locale)
                raw_coordinates = next(line for line in self.items[identity]['guide']['preparation']
                                       if line.startswith('Position tridimensionnelle : '))
                self.assertIn(space + raw_coordinates.split(' : ', 1)[1], korok['guide']['preparation'])
                quest = self.rendered_item('quetes_secondaires:rushroomrush', locale)
                self.assertIn(step, [item['title'] for item in quest['guide']['steps']])
                chest = self.rendered_item('coffres_monde:AocField-452454445', locale)
                self.assertIn(sector, [item['instruction'] for item in chest['guide']['steps']])
                trials = self.rendered_item('epreuves_epee:epreuves-expert', locale)
                self.assertEqual(trials['guide']['trial_rooms'][0]['enemies'], enemy)

    def test_english_korok_guide_names_the_reward_in_each_field(self):
        identity = 'korogus:MainField_Npc_HiddenKorokGround_3077381654'
        guide = self.rendered_item(identity, 'en')['guide']
        self.assertEqual(guide['steps'][-1]['title'], 'Collect the Korok Seed')
        self.assertEqual(guide['steps'][-1]['instruction'],
                         'Talk to the Korok that appeared and collect the Korok Seed.')
        self.assertEqual(guide['completion']['condition'],
                         'The Korok must award the Korok Seed and its individual flag must be set.')

    def test_upgrade_diagnostics_accept_display_values_without_case_agreement(self):
        for identity in ('legacy-diagnostic-3', 'legacy-diagnostic-4'):
            for value in ('1', '2', '4', '1\u00a0000'):
                with self.subTest(message=identity, value=value):
                    result, errors = self.bundle.format_pattern(
                        self.bundle.get_message(identity).value, {'value0': value})
                    self.assertEqual(errors, [])
                    self.assertTrue(result.startswith(f'Улучшение брони. Уровень (звёзд): {value}. '))

    def test_editorial_records_describe_the_committed_resources(self):
        editorial = read(ROOT / 'docs/RUSSIAN_EDITORIAL_REVIEW.json')
        source = (ROOT / 'botw_companion/locales/ru/messages.ftl').read_text(encoding='utf-8')
        for section in (editorial, editorial['maintainer_review_2026_11_09']):
            for entry in section['prose_changes']:
                with self.subTest(key=entry['key']):
                    self.assertEqual(self.prose[entry['key']], entry['after'])
            for entry in section['ftl_changes']:
                self.assertIn(entry['after'], source)
