from pathlib import Path
import unittest

from botw_companion.i18n.presentation import Presenter
from tools.i18n import read

ROOT = Path(__file__).resolve().parents[1]


class RussianNameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.game = read(ROOT / 'botw_companion/locales/ru/game.json')
        cls.source = read(ROOT / 'botw_companion/locales/fr/game.json')
        cls.english = read(ROOT / 'botw_companion/locales/en/game.json')
        cls.review = read(ROOT / 'docs/RUSSIAN_NAME_REVIEW.json')
        cls.audit = read(ROOT / 'docs/RUSSIAN_TERMINOLOGY_AUDIT.json')

    def test_names_and_trials_cover_all_canonical_identities(self):
        self.assertEqual(self.game.keys(), self.source.keys())
        for section, entries in self.source.items():
            with self.subTest(section=section):
                actual = self.game[section]
                self.assertEqual(actual.keys(), entries.keys())
                self.assertTrue(all(isinstance(value, str) and value.strip()
                                    for value in actual.values()))

    def test_provenance_covers_each_identity_and_matches_locale_values(self):
        terms = self.review['terms']
        for section, field in [('names_by_id', 'mappings'),
                               ('trials_by_id', 'trial_mappings')]:
            records = self.review[field]
            indexed = {record['id']: record for record in records}
            self.assertEqual(len(indexed), len(records), field)
            self.assertEqual(indexed.keys(), self.game[section].keys(), field)
            for identity, record in indexed.items():
                with self.subTest(section=section, identity=identity):
                    self.assertEqual(record['russian'], self.game[section][identity])
                    self.assertEqual(record['english'], self.english[section][identity])
                    if section == 'names_by_id':
                        self.assertIn(record['term'], terms)
                        self.assertTrue(record['method'])
                        self.assertTrue(terms[record['term']]['source'])
                        for component in record.get('component_terms', []):
                            self.assertIn(component, terms)
                    else:
                        self.assertTrue(record['source'])
                        self.assertIsInstance(record['has_game_citation'], bool)

    def test_provisional_decisions_agree_with_the_name_review(self):
        records = self.audit['results']
        indexed = {record['english']: record for record in records}
        pending = self.review['provisional_terms_for_botw_review']
        self.assertEqual(len(indexed), len(records))
        self.assertEqual(indexed.keys(), pending.keys())
        self.assertEqual(self.audit['terms_reviewed'], len(records))
        self.assertEqual(self.audit['retained'], sum(record['decision'] == 'retain'
                                                    for record in records))
        self.assertEqual(self.audit['renamed'], sum(record['russian_before'] != record['russian_after']
                                                   for record in records))
        for term, record in indexed.items():
            with self.subTest(term=term):
                entry = pending[term]
                self.assertEqual(record['russian_after'], entry['russian'])
                editorial = entry['editorial_review_2026_10_24']
                for field in ('decision', 'evidence_status', 'note', 'sources_checked'):
                    self.assertEqual(record[field], editorial[field])
                if term in self.review['terms']:
                    self.assertEqual(record['russian_after'], self.review['terms'][term]['russian'])

    def test_name_presentation_preserves_technical_and_personal_values(self):
        reference = {
            **self.game,
            'strings': {},
            'glossary': {term: entry['russian'] for term, entry in self.review['terms'].items()},
            'patterns': [],
        }
        presenter = Presenter('ru', reference=reference)
        for key, expected in self.game['names_by_id'].items():
            category, identity = key.split(':', 1)
            original = {
                'category': category, 'id': identity,
                'name': self.english['names_by_id'][key],
                'flag': 'Clear_Dungeon000', 'hash': 123,
                'acteur': 'Enemy_Lynel_Gold', 'x': 1.25, 'z': -2.5,
                'note_personnelle': 'Apple, Dungeon135 and my own note',
                'source_url': 'https://example.invalid/Apple',
            }
            with self.subTest(identity=key):
                result = presenter.present(original)
                self.assertEqual(result, {**original, 'name': expected})
        for identity, expected in self.game['trials_by_id'].items():
            original = {'category': 'shrines', 'id': identity,
                        'trial': self.english['trials_by_id'][identity]}
            with self.subTest(trial=identity):
                self.assertEqual(presenter.present(original), {**original, 'trial': expected})
