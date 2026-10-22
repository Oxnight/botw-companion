import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import unittest

from botw_companion.i18n import locale_resource
from botw_companion.i18n.presentation import translate_text, TECHNICAL_VALUE
from botw_companion.resources import load_catalog


class Snapshot(HTMLParser):
    def __init__(self):
        super().__init__()
        self.events = []
        self.ignore_script = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'meta' and values.get('name') == 'botw-localization-error':
            return
        if tag == 'script' and values.get('src', '').split('?')[0] in ('/locale.js', '/i18n.js'):
            self.ignore_script = True
            return
        self.events.append(['start', tag, attrs])

    def handle_endtag(self, tag):
        if tag == 'script' and self.ignore_script:
            self.ignore_script = False
            return
        self.events.append(['end', tag])

    def handle_data(self, value):
        if value.strip() and not self.ignore_script:
            self.events.append(['text', value.strip()])

    def digest(self):
        return hashlib.sha256(json.dumps(self.events, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()


class HtmlCompatibilityTests(unittest.TestCase):
    def test_french_term_inputs_match_canonical_names_by_stable_identity(self):
        package = Path(__file__).resolve().parents[1] / 'botw_companion'
        french = json.loads((package / 'locales/fr/game.json').read_text(encoding='utf-8'))
        catalog = load_catalog()
        names = {group + ':' + str(item['id']): item['name']
                 for group, items in catalog.items() if isinstance(items, list)
                 for item in items if isinstance(item, dict) and item.get('id') and item.get('name')}
        trials = {str(item['id']): item['trial'] for item in catalog['shrines']}
        self.assertEqual(french['names_by_id'], {key: names[key] for key in french['names_by_id']})
        self.assertEqual(french['trials_by_id'], {key: trials[key] for key in french['trials_by_id']})

    def test_generated_backend_cache_matches_captured_prose_and_preserves_protocol_values(self):
        fixtures = Path(__file__).with_name('fixtures')
        reference = json.loads((fixtures / 'corpus_compatibility.json').read_text(encoding='utf-8'))
        package = Path(__file__).resolve().parents[1] / 'botw_companion'
        prose = json.loads((package / 'locales/en/prose.json').read_text(encoding='utf-8'))['strings']
        source = json.loads((package / 'i18n/cache-source.json').read_text(encoding='utf-8'))
        keys = set(prose) | set(source)
        presentation = {key: translate_text(key, 'en') for key in keys if not TECHNICAL_VALUE.fullmatch(key)}
        self.assertEqual(len(keys), reference['total_inputs'])
        self.assertEqual(len(presentation), reference['presentation_inputs'])
        digest = hashlib.sha256(json.dumps(presentation, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
        self.assertEqual(digest, reference['presentation_sha256'])
        for key in keys:
            if TECHNICAL_VALUE.fullmatch(key):
                self.assertEqual(translate_text(key, 'en'), key)

    def test_both_published_documents_preserve_all_original_dom_attributes_and_text(self):
        reference = json.loads(Path(__file__).with_name('fixtures').joinpath('html_compatibility.json').read_text(encoding='utf-8'))
        for locale, expected in reference['locales'].items():
            with self.subTest(locale=locale):
                parser = Snapshot()
                document = locale_resource('index.html', locale).read_text(encoding='utf-8')
                parser.feed(document)
                self.assertEqual(parser.digest(), expected['events_sha256'])
                self.assertLess(document.index('/locale.js?'), document.index('/i18n.js'))
                self.assertLess(document.index('/i18n.js'), document.index('/language.js'))
                self.assertLess(document.index('/language.js'), document.index('/browser_session.js'))
