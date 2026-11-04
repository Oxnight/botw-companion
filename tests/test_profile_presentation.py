import copy
import unittest

from botw_companion.i18n.presentation import Presenter, present, translate_text
from botw_companion.resources import load_completion_standard


class ProfilePresentationTests(unittest.TestCase):
    def test_profile_scope_is_display_prose_but_other_scopes_are_preserved(self):
        source = 'Profil base ou DLC choisi depuis les preuves présentes dans la sauvegarde, limité aux validations automatiques.'
        presenter = Presenter('test', reference={
            'strings': {source: 'Translated profile description'},
            'glossary': {}, 'patterns': [], 'names_by_id': {},
        })
        profile = {'id': 'automatic', 'label': 'Automatic', 'scope': source,
                   'progress': {'total': 10}, 'metadata': {'scope': source}}
        result = presenter.present(profile)
        self.assertEqual(result['scope'], 'Translated profile description')
        self.assertEqual(result['metadata']['scope'], source)
        self.assertEqual(profile['scope'], source)
        self.assertEqual(presenter.present({'scope': 'base_game'}), {'scope': 'base_game'})

    def test_published_profile_descriptions_use_reviewed_english_and_preserve_state(self):
        standard = load_completion_standard()
        expected = {
            'base': 'Permanent automatic objectives in the base game, excluding the Expansion Pass, Xenoblade update, amiibo, manual tracking and Master Mode.',
            'dlc': 'Automatic objectives in the base game, Expansion Pass and Xenoblade update, excluding amiibo, manual tracking and Master Mode.',
            'automatique': 'Base-game or DLC profile selected from evidence in the save, limited to automatically tracked objectives.',
            'amiibo': 'Exclusive items that depend on the amiibo you own and random drops.',
            'expert': 'Automatically tracked progress in the Master Mode save, separate from the six Normal Mode save slots and manual tracking.',
            'carte': 'Official map counter, excluding quests, chests, memories and the Hyrule Compendium.',
        }
        profiles = [{**profile, 'progress': {'total': 10, 'done': 3, 'remaining': 7}}
                    for profile in standard['profiles']]
        original = copy.deepcopy(profiles)
        french = present(profiles, 'fr')
        english = present(profiles, 'en')
        self.assertEqual(french, original)
        self.assertEqual(profiles, original)
        for source, result in zip(profiles, english):
            self.assertEqual(result['scope'], expected[source['id']])
            for field in ('id', 'required', 'axes', 'progress'):
                self.assertEqual(result[field], source[field])
        for category in standard['categories']:
            self.assertEqual(present(category, 'en')['scope'], category['scope'])

    def test_added_labels_and_mechanics_are_translated_in_english(self):
        pairs = {
            "Compendium d'Hyrule": 'Hyrule Compendium', 'Yigas fixes': 'Fixed Yiga encounters',
            'appareil gyroscopique': 'motion-controlled apparatus',
            'bombes et trajectoires': 'bombs and trajectories', 'courants ascendants': 'updrafts',
            "cryonis et niveau d'eau": 'Cryonis and water level',
            'observation et symboles': 'observation and symbols',
            'parcours et construction': 'traversal and construction',
            'sanctuaires jumeaux': 'twin shrines', 'tutoriel de combat': 'combat tutorial',
        }
        for source, expected in pairs.items():
            with self.subTest(source=source):
                self.assertEqual(translate_text(source, 'en'), expected)
                self.assertEqual(translate_text(source, 'fr'), source)


if __name__ == '__main__':
    unittest.main()
