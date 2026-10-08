import copy
import http.client
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unittest

from botw_companion.analyzer import analyze
from botw_companion.english import english_presentation, translate_text, TECHNICAL_FIELDS
from botw_companion.quest_walkthroughs import QUEST_WALKTHROUGHS
from tools.build_english_assets import markup, english_morphology
from tools.localization_checks import has_french_prose, has_bad_english
import test_server_security as server_fixture

ROOT = Path(__file__).resolve().parents[1]


class Controls(HTMLParser):
    def __init__(self):
        super().__init__()
        self.controls = []
        self.visible = []

    def handle_starttag(self, tag, attrs):
        self.visible.extend(v for k, v in attrs if k in {'aria-label', 'title', 'placeholder', 'alt'} and v)
        if tag in {'button', 'input', 'select', 'option', 'textarea'}:
            self.controls.append((tag, {k: v for k, v in attrs
                if k not in {'aria-label', 'title', 'placeholder', 'alt'}}))

    def handle_data(self, data):
        if data.strip(): self.visible.append(data.strip())


class EnglishTests(unittest.TestCase):
    def test_complete_html_templates_keep_technical_attributes(self):
        source = '<button class="coffres" data-id="ZXQ0QXZ" title="Voir sur la carte" aria-label="Voir ZXQ1QXZ sur la carte">Carte</button>'
        expected = '<button class="coffres" data-id="ZXQ0QXZ" title="View on map" aria-label="View ZXQ1QXZ on the map">Map</button>'
        self.assertEqual(markup(source), expected)
        self.assertEqual(english_morphology('${count} completed${count > 1 ? "s" : ""}'), '${count} completed')
        self.assertEqual(english_morphology('${count} chest${count > 1 ? "s" : ""}'), '${count} chest${count > 1 ? "s" : ""}')

    def test_official_terms_inside_instructions_and_item_variants(self):
        pairs = {'Cinetis': 'Stasis', 'Tetralame Mort-Subite': 'One-Hit Obliterator',
                 'Armure de Spectre': 'Phantom Armor', 'Armure spectrale': 'Phantom Ganon Armor',
                 'Jambières de Spectre': 'Phantom Greaves', 'Grèves spectrales': 'Phantom Ganon Greaves',
                 'Casque de Spectre': 'Phantom Helmet', 'Masque spectral': 'Phantom Ganon Skull',
                 'Marmite': 'Cooking Pot', 'Radeau': 'Raft', 'Onag': 'Prima'}
        for french, english in pairs.items():
            self.assertEqual(translate_text(french), english, french)
        for french, english in [('Bouclier', 'Guardian Shield'), ('Lance', 'Guardian Spear'), ('Glaive', 'Guardian Sword')]:
            for level in (1, 2, 3):
                self.assertEqual(translate_text(f'{french} de Gardien {level}.0'), english + '+' * (level - 1))
        self.assertIn('One-Hit Obliterator', translate_text(QUEST_WALKTHROUGHS['BalladOfHeroes']['steps'][0]))
        self.assertIn('Fireblight Ganon', translate_text(QUEST_WALKTHROUGHS['Fire_Relic']['steps'][2]))
        self.assertEqual(translate_text("Colère d'Urbosa"), "Urbosa's Fury")
        self.assertEqual(translate_text('Réceptacle de cœur'), 'Heart Container')
        self.assertEqual(translate_text('Rage de Revali'), "Revali's Gale")
        instruction = 'Observe les motifs, constellations, ombres ou sources lumineuses et reproduis leur ordre sur les interrupteurs.'
        self.assertIn('reproduce their order', translate_text(instruction))
        self.assertIn('Meteo Wizzrobe', translate_text('1 Sorcier météore, 2 Bokoblins bleus, 1 Bokoblin noir'))
        self.assertIn('3:00 PM', translate_text("Attends environ 15 h puis place-toi sur le socle lorsque l'ombre de la tour passe dessus."))
        self.assertIn('trunk', translate_text('Ajuste la trompe sur la carte, utilise Cryonis ou Polaris selon la salle et récupère le coffre avant de changer de configuration.'))

    def test_quest_characters_are_correct_in_both_languages(self):
        rito = QUEST_WALKTHROUGHS['RitoSongMystery']['steps'][0]
        beloved = QUEST_WALKTHROUGHS['HatenoMini_LoveInsects']['steps'][0]
        self.assertIn('Della', rito)
        self.assertIn('Onag', beloved)
        self.assertNotIn('Dézelle', rito + beloved)
        self.assertIn('Bedoli', translate_text(rito))
        self.assertIn('Prima', translate_text(beloved))
        monuments = QUEST_WALKTHROUGHS['ZoraMini_ReliefSearch']['steps'][0]
        giant = QUEST_WALKTHROUGHS['Giant_ZoraMini']['steps'][0]
        self.assertIn('Jitato', monuments)
        self.assertIn('Jiahto', translate_text(monuments))
        self.assertIn('Poréa', giant)
        self.assertIn('Torfeau', translate_text(giant))
        self.assertIn("Zora's Domain", translate_text(giant))

    def test_bilingual_invalid_payload_errors_are_localized(self):
        fixture = server_fixture.ServerSecurityTests()
        with fixture.running_server() as (_, port, _):
            for language, expected in [('fr', 'JSON invalide'), ('en', 'Invalid JSON')]:
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                try:
                    connection.request('PUT', '/api/preferences?lang=' + language, body=b'{invalid',
                                       headers={'Content-Type': 'application/json',
                                                'X-BOTW-Session-Token': fixture.TOKEN})
                    response = connection.getresponse()
                    self.assertEqual(response.status, 400)
                    self.assertEqual(response.getheader('Content-Language'), language)
                    self.assertEqual(json.loads(response.read())['erreur'], expected)
                finally:
                    connection.close()

    def test_official_identifiers_resolve_variants_and_keep_guides_consistent(self):
        original = {'id': 'Weapon_Lsword_015', 'name': 'Hache de Gardien 1.0',
                    'flag': 'IsGet_Weapon_Lsword_015', 'x': 123,
                    'guide': {'summary': 'Hache de Gardien 1.0'}}
        frozen = copy.deepcopy(original)
        result = english_presentation(original)
        self.assertEqual(result['name'], 'Ancient Battle Axe++')
        self.assertEqual(result['guide']['summary'], 'Ancient Battle Axe++')
        self.assertEqual(result['flag'], original['flag'])
        self.assertEqual(result['x'], 123)
        self.assertEqual(original, frozen)

    def test_shrine_chests_and_materials_have_official_names(self):
        self.assertEqual(translate_text('Coffre - Sanctuaire de Ta\'Mur'), 'Chest - Tah Muhl Shrine')
        self.assertEqual(english_presentation({'id': 'Armor_116_Upper', 'name': 'Tunique du Prodige'})['name'], "Champion's Tunic")
        self.assertEqual(translate_text('Princesse de la sérénité'), 'Silent Princess')

    def test_dynamic_messages_retain_values(self):
        self.assertEqual(translate_text('Progression interne 27'), 'Internal progression 27')
        value = translate_text('Ressource DSU Windows absente : JoyConDSU.exe')
        self.assertIn('JoyConDSU.exe', value)
        self.assertNotIn('absente', value)
        diagnostic = translate_text('Ressource DSU Windows absente : /tmp/Cocorico/installer.exe')
        self.assertEqual(diagnostic, 'Missing Windows DSU resource: /tmp/Cocorico/installer.exe')
        self.assertEqual(translate_text('JSON invalide'), 'Invalid JSON')
        self.assertEqual(translate_text('Dossier introuvable : /tmp/Cocorico/save'), 'Folder not found: /tmp/Cocorico/save')
        self.assertEqual(translate_text('Tableau GameData 0x5f283289 introuvable'), 'GameData array 0x5f283289 not found')

    def test_personal_data_and_protocol_values_are_preserved(self):
        original = {'note_personnelle': 'Marlon à Cocorico', 'categorie': 'sanctuaires',
                    'status': 'termine', 'source_url': 'https://example.com/fr',
                    'strategy': 'region', 'x': 12.75, 'z': -45.2}
        result = english_presentation(original)
        self.assertEqual(result, original)
        self.assertEqual(english_presentation({'members': ['objets_speciaux:destrier-zero-un', 'coffre_arme_une_main']}),
                         {'members': ['objets_speciaux:destrier-zero-un', 'coffre_arme_une_main']})
        self.assertEqual(translate_text('Destrier de légende 0.1'), 'Master Cycle Zero')
        self.assertEqual(translate_text('Filet monstrueux'), 'Monster Bridle')

    def test_html_controls_keep_identifiers_and_values_in_both_languages(self):
        french, english = Controls(), Controls()
        french.feed((ROOT / 'botw_companion/web/index.html').read_text(encoding='utf-8'))
        english.feed((ROOT / 'botw_companion/web/index_en.html').read_text(encoding='utf-8'))
        self.assertEqual(french.controls, english.controls)
        self.assertIn('Help', english.visible)
        self.assertNotIn('Aide', english.visible)
        for text in ['SAUVEGARDE', 'Plus tard', 'Exporter', 'Importer', 'Vue d’ensemble']:
            self.assertNotIn(text, english.visible)
        self.assertNotRegex(' '.join(english.visible), r'[éèàùçœ]')

    def test_shared_browser_assets_are_independent_of_language_cookies(self):
        fixture = server_fixture.ServerSecurityTests()
        with fixture.running_server() as (_, port, _):
            for path in ['/style.css', '/metrics.css', '/armor.css', '/language.js']:
                _, french, fr_headers = fixture.request(port, 'GET', path, headers={'Cookie': 'botw-language=fr'})
                status, english, en_headers = fixture.request(port, 'GET', path, headers={'Cookie': 'botw-language=en'})
                self.assertEqual(status, 200)
                self.assertEqual(french, english, path)
                self.assertNotIn('Vary', fr_headers)
                self.assertNotIn('Vary', en_headers)
                self.assertEqual(en_headers['Cache-Control'], 'no-store')
                if path.endswith('.css'):
                    self.assertNotIn(b'var(--text)', english)
                    self.assertNotIn(b'var(--muted)', english)
                    if path == '/style.css':
                        self.assertIn(b'color: #f2f4eb', english)
                    if path == '/metrics.css':
                        self.assertIn(b'var(--progress, 0%)', english)
            _, _, headers = fixture.request(port, 'GET', '/app.js?lang=en')
            self.assertEqual(headers['Content-Language'], 'en')
            self.assertEqual(headers['Cache-Control'], 'no-store')
            self.assertIn('Cookie', headers['Vary'])

    def test_language_is_per_request_and_does_not_mutate_the_cached_report(self):
        fixture = server_fixture.ServerSecurityTests()
        payload = {'label': 'Sanctuaires', 'elements': [], 'categories': {},
                   'sauvegarde': {'slot': 1, 'date': 'today'}}
        with fixture.running_server(payload_factory=lambda: payload) as (_, port, _):
            status, body, headers = fixture.request(port, 'GET', '/api/report?lang=en')
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['label'], 'Shrines')
            self.assertEqual(headers['Content-Language'], 'en')
            status, body, headers = fixture.request(port, 'GET', '/api/report?lang=fr')
            self.assertEqual(json.loads(body)['label'], 'Sanctuaires')
            self.assertEqual(headers['Content-Language'], 'fr')
            for path, supplied, expected in [
                ('/api/report', {'Cookie': 'botw-language=en'}, 'en'),
                ('/api/report', {'Cookie': 'botw-language=en', 'X-BOTW-Language': 'fr'}, 'fr'),
                ('/api/report?lang=en', {'X-BOTW-Language': 'fr'}, 'en'),
            ]:
                status, body, headers = fixture.request(port, 'GET', path, headers=supplied)
                self.assertEqual(status, 200)
                self.assertEqual(headers['Content-Language'], expected)
            for path, lang in [('/?lang=en', 'en'), ('/?lang=fr', 'fr')]:
                status, body, _ = fixture.request(port, 'GET', path)
                self.assertEqual(status, 200)
                self.assertIn(f'<html lang="{lang}">'.encode(), body)
                self.assertIn(fixture.TOKEN.encode(), body)
            note = 'Mon texte en français — Marlon à Cocorico'
            status, body, _ = fixture.request(port, 'PUT', '/api/manual/sanctuaires%3ADungeon000?lang=en',
                body={'completed': False, 'note': note, 'expected_revision': 0},
                headers={'X-BOTW-Session-Token': fixture.TOKEN})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)['entries']['sanctuaires:Dungeon000']['note'], note)
            for path in ['/api/manual', '/api/manual/export', '/api/routes', '/api/routes/export', '/api/preferences', '/api/backup/export']:
                _, a, english_headers = fixture.request(port, 'GET', path+'?lang=en')
                b = fixture.request(port, 'GET', path+'?lang=fr')[1]
                first, second = json.loads(a), json.loads(b)
                if path == '/api/backup/export':
                    first.pop('exported_at', None)
                    second.pop('exported_at', None)
                self.assertEqual(first, second, path)
                if path.endswith('/export'):
                    expected = {'/api/manual/export': 'manual-tracking', '/api/routes/export': 'routes', '/api/backup/export': 'backup'}[path]
                    self.assertEqual(english_headers['Content-Disposition'], f'attachment; filename=botw-companion-{expected}.json')
        self.assertEqual(payload['label'], 'Sanctuaires')

    def test_full_report_translation_keeps_game_state_and_has_no_french_prose(self):
        original = analyze({})
        translated = english_presentation(original)
        failures = []
        def walk(a, b, field=''):
            if field in TECHNICAL_FIELDS or field.endswith(('_flag', '_path', '_id', '_url', '_sha256')):
                self.assertEqual(a, b)
                return
            if isinstance(a, dict):
                self.assertEqual(a.keys(), b.keys())
                for k in a: walk(a[k], b[k], k)
            elif isinstance(a, list):
                self.assertEqual(len(a), len(b))
                for x, y in zip(a, b): walk(x, y, field)
            elif isinstance(a, str):
                if re.fullmatch(r'(?:[a-z][a-z0-9_]*:[A-Za-z0-9_:.-]+|[a-z][a-z0-9]*_[a-z0-9_]+)', a):
                    self.assertEqual(a, b)
                    return
                self.assertEqual(re.findall(r'\b[XYZ] -?\d+(?:\.\d+)?', a),
                                 re.findall(r'\b[XYZ] -?\d+(?:\.\d+)?', b), a[:100])
                if has_french_prose(b) or has_bad_english(b):
                    failures.append((field, a, b))
            else: self.assertEqual(a, b)
        walk(original, translated)
        self.assertEqual(len(failures), 0, str(failures[:5]))
        self.assertEqual(original['categories']['sanctuaires']['label'], 'Sanctuaires')
