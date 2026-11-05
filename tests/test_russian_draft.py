"""Validate supplied resources of the deliberately disabled Russian draft."""
import json
from pathlib import Path
import unittest
from fluent.syntax import FluentParser, ast
from tools.i18n import parse_messages

ROOT = Path(__file__).resolve().parents[1]

class RussianDraftTests(unittest.TestCase):
    def test_supplied_messages_follow_the_shared_contract(self):
        folder = ROOT / 'botw_companion/locales/ru'
        contract = json.loads((ROOT / 'botw_companion/i18n/contract.json').read_text('utf-8'))
        tree = FluentParser().parse((folder / 'messages.ftl').read_text('utf-8'))
        identities = {n.id.name for n in tree.body if isinstance(n, ast.Message)}
        self.assertTrue(identities)
        self.assertLessEqual(identities, contract.keys())
        parse_messages(folder / 'messages.ftl', {k: contract[k] for k in identities})

    def test_draft_stays_disabled_and_supplied_json_uses_canonical_keys(self):
        folder = ROOT / 'botw_companion/locales/ru'
        self.assertIs(json.loads((folder / 'locale.json').read_text('utf-8'))['enabled'], False)
        for filename in ('game.json', 'prose.json'):
            expected = json.loads((folder.parent / 'fr' / filename).read_text('utf-8'))
            supplied = json.loads((folder / filename).read_text('utf-8'))
            self.assertEqual(supplied.keys(), expected.keys())
            for section, values in supplied.items():
                self.assertLessEqual(values.keys(), expected[section].keys())
                self.assertTrue(all(isinstance(v, str) and v.strip() for v in values.values()))

    def test_point_count_uses_russian_plural_forms_and_formatted_count(self):
        from fluent.runtime import FluentBundle, FluentResource
        source = (ROOT / 'botw_companion/locales/ru/messages.ftl').read_text('utf-8')
        bundle = FluentBundle(['ru-RU'], use_isolating=False)
        bundle.add_resource(FluentResource(source))
        pattern = bundle.get_message('renderfilternav-point-count').value
        for count, suffix in [(0, 'точек'), (1, 'точка'), (2, 'точки'),
                              (5, 'точек'), (11, 'точек'), (21, 'точка'),
                              (22, 'точки'), (25, 'точек'), (101, 'точка')]:
            with self.subTest(count=count):
                text, errors = bundle.format_pattern(pattern, {'count': count,
                                                               'formattedCount': str(count)})
                self.assertEqual(errors, [])
                self.assertEqual(text, f'{count} {suffix}')
