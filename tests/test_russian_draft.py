import json
from pathlib import Path
import unittest

from fluent.runtime import FluentBundle, FluentResource
from fluent.syntax import FluentParser, ast

from tools.i18n import manifests, parse_messages

ROOT = Path(__file__).resolve().parents[1]


class RussianDraftTests(unittest.TestCase):
    def setUp(self):
        self.folder = ROOT / 'botw_companion/locales/ru'
        self.source = (self.folder / 'messages.ftl').read_text(encoding='utf-8')
        self.bundle = FluentBundle(['ru-RU'], use_isolating=False)
        self.bundle.add_resource(FluentResource(self.source))

    def format_message(self, identity, **values):
        pattern = self.bundle.get_message(identity).value
        text, errors = self.bundle.format_pattern(pattern, values)
        self.assertEqual(errors, [], identity)
        return text

    def test_supplied_messages_follow_the_shared_contract(self):
        contract = json.loads((ROOT / 'botw_companion/i18n/contract.json').read_text(encoding='utf-8'))
        tree = FluentParser().parse(self.source)
        identities = {n.id.name for n in tree.body if isinstance(n, ast.Message)}
        self.assertTrue(identities)
        self.assertLessEqual(identities, contract.keys())
        parse_messages(self.folder / 'messages.ftl', {k: contract[k] for k in identities})
        html_contract = json.loads((ROOT / 'botw_companion/i18n/html.json').read_text(encoding='utf-8'))
        self.assertLessEqual(html_contract.keys(), identities)

    def test_draft_stays_disabled_and_supplied_json_uses_canonical_keys(self):
        self.assertIs(json.loads((self.folder / 'locale.json').read_text(encoding='utf-8'))['enabled'], False)
        registry = manifests(ROOT / 'botw_companion')
        self.assertNotIn('ru', registry['locales'])
        self.assertNotIn('ru', registry['aliases'].values())
        for filename in ('game.json', 'prose.json'):
            expected = json.loads((self.folder.parent / 'fr' / filename).read_text(encoding='utf-8'))
            supplied = json.loads((self.folder / filename).read_text(encoding='utf-8'))
            self.assertEqual(supplied.keys(), expected.keys())
            for section, values in supplied.items():
                self.assertLessEqual(values.keys(), expected[section].keys())
                self.assertTrue(all(isinstance(v, str) and v.strip() for v in values.values()))

    def test_point_count_uses_russian_plural_forms_and_formatted_count(self):
        for count, suffix in [(0, 'точек'), (1, 'точка'), (2, 'точки'),
                              (5, 'точек'), (11, 'точек'), (21, 'точка'),
                              (22, 'точки'), (25, 'точек'), (101, 'точка'),
                              (-1, 'точка'), (-2, 'точки'), (-11, 'точек'),
                              (1.5, 'точки')]:
            with self.subTest(count=count):
                text = self.format_message('renderfilternav-point-count', count=count,
                                           formattedCount=str(count))
                self.assertEqual(text, f'{count} {suffix}')
        self.assertEqual(self.format_message('renderfilternav-point-count', count=1000,
                                            formattedCount='1\u00a0000'), '1\u00a0000 точек')

    def test_route_list_actions_use_the_correct_case_and_keep_the_objective_name(self):
        for remove, action, preposition, expected, ending in [
            (False, 'add', 'at', 'Добавить в маршрут', 'в маршрут'),
            (True, 'remove', 'of', 'Удалить из маршрута', 'из маршрута'),
        ]:
            with self.subTest(remove=remove):
                fragment = self.format_message('renderitems-remove-from' if remove else 'renderitems-add-to')
                self.assertEqual(self.format_message('renderitems-the-route', value5=fragment), expected)
                for name in ('Святилище', 'Цель «A&B»'):
                    text = self.format_message('renderitems-the-route-2',
                        value2=self.format_message('renderitems-' + action), value3=name,
                        value4=self.format_message('renderitems-' + preposition))
                    verb = 'Удалить' if remove else 'Добавить'
                    self.assertEqual(text, f'{verb} {name} {ending}')

    def test_detail_route_actions_keep_markup_and_use_the_correct_case(self):
        markup = {
            'value9': '<button id="detailRoute">', 'value8': '</button>',
            'value7': '<button id="detailCenter">', 'value6': '</button>',
            'value5': '<button id="copyCoords">', 'value4': '</button>',
            'value3': '<a href="https://objmap.zeldamods.org/">', 'value2': '</a>',
        }
        for identity, expected in [('renderdetails-add-to', 'Добавить в маршрут'),
                                   ('renderdetails-remove-from', 'Удалить из маршрута')]:
            with self.subTest(action=identity):
                text = self.format_message('renderdetails-the-route-center-on-the-map-copy',
                    value0=self.format_message(identity), **markup)
                self.assertEqual(text, f'<button id="detailRoute">{expected}</button>'
                    '<button id="detailCenter">Показать в центре карты</button>'
                    '<button id="copyCoords">Скопировать основную точку</button>'
                    '<a href="https://objmap.zeldamods.org/">ObjMap ↗</a>')

    def test_diagnostic_counters_keep_formatted_values_without_case_agreement(self):
        for first, second in [('0', '1'), ('1', '2'), ('5', '21'), ('1\u00a0000', '7')]:
            with self.subTest(first=first, second=second):
                values = {'value0': first, 'value1': second}
                self.assertEqual(self.format_message(
                    'renderdsudiagnostic-duplicates-timestamps-out-of-order', **values),
                    f'Повторы: {first} • временные метки с нарушенным порядком: {second}')
                self.assertEqual(self.format_message(
                    'renderdsudiagnostic-udp-invalid-requests', **values),
                    f'UDP: {first} • некорректные запросы: {second}')
