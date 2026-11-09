from pathlib import Path
import re
import unittest

from fluent.runtime import FluentBundle, FluentResource

from botw_companion.i18n.presentation import Presenter
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
        cls.presenter = Presenter('ru', reference={
            'strings': cls.prose, 'glossary': {}, 'patterns': [],
            **read(folder / 'game.json'),
        })

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

    def test_rushroom_quest_keeps_its_factual_quantity(self):
        for key in ('Récolte cinquante champignons tempo sans les cuisiner.',
                    'Vends les cinquante champignons à Pirou en une fois.'):
            with self.subTest(key=key):
                result = self.presenter.translate_text(key)
                self.assertIn('55 прытковиков', result)
                self.assertNotIn('пятьдесят', result)

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
