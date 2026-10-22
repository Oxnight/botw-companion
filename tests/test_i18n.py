from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, ExitStack, redirect_stdout
import copy
import hashlib
import html
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from fluent.syntax import FluentParser, FluentSerializer, ast

from botw_companion import i18n
from botw_companion.i18n import presentation
from botw_companion.launcher_support import launcher_error, saved_language, remember_language
from botw_companion.manual_tracking import ManualTrackingStore
from botw_companion.preferences import PreferenceStore
from botw_companion.route_sessions import RouteSessionStore
from botw_companion.runtime_state import RuntimeStateStore
from botw_companion.server import serve
from tools import i18n as builder

ROOT = Path(__file__).resolve().parents[1]
COUNTS = [0, 1, 2, 4, 5, 11, 14, 21, 22, 25, 101, -1, -2, -11, 0.1, 1.2, 2.5, 1000]
PROBES = '''
probe-count = { $count ->
    [zero] zero
    [one] one
    [two] two
    [few] few
    [many] many
   *[other] other
    }
probe-number = { NUMBER($count, useGrouping: 0, maximumFractionDigits: 2) }
probe-values = { $first } / { $second } / { $first }
probe-rich = { $open }<img onerror="throw 1">{ $name }{ $close }
'''


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def fingerprint(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


@contextmanager
def loaded(package):
    original = i18n.files
    def resources(name):
        if name == 'botw_companion':
            return package
        if name == 'botw_companion.web':
            return package / 'web'
        return original(name)
    i18n.registry.cache_clear(); i18n.settings.cache_clear(); i18n.catalog.cache_clear(); i18n.contracts.cache_clear()
    presentation.presenter.cache_clear()
    try:
        with patch.object(i18n, 'files', resources), patch.object(presentation, 'files', resources):
            yield
    finally:
        i18n.registry.cache_clear(); i18n.settings.cache_clear(); i18n.catalog.cache_clear(); i18n.contracts.cache_clear()
        presentation.presenter.cache_clear()


class LocalizationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='botw-i18n-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'пакет'
        self.package = self.root / 'botw_companion'
        self.package.mkdir(parents=True)
        shutil.copytree(ROOT / 'botw_companion/i18n', self.package / 'i18n', ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(ROOT / 'botw_companion/locales', self.package / 'locales')
        (self.package / 'web').mkdir()
        for name in ('index.template.html', 'i18n.js', 'app.js', 'route_planner.js', 'language.js', 'browser_session.js'):
            shutil.copyfile(ROOT / 'botw_companion/web' / name, self.package / 'web' / name)
        for name in ('pyproject.toml', '.github/workflows/release.yml',
                     'windows/BOTW Companion.spec', 'macos/BOTW Companion.spec', 'tools/i18n.py'):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        contract = builder.read(self.package / 'i18n/contract.json')
        contract.update({'probe-count': {'params': ['count'], 'rich': False, 'markup': []},
                         'probe-number': {'params': ['count'], 'rich': False, 'markup': []},
                         'probe-values': {'params': ['first', 'second'], 'rich': False, 'markup': []},
                         'probe-rich': {'params': ['open', 'name', 'close'], 'rich': True, 'markup': ['open', 'close']}})
        write(self.package / 'i18n/contract.json', contract)
        for locale in ('fr', 'en'):
            with (self.package / 'locales' / locale / 'messages.ftl').open('a', encoding='utf-8') as out:
                out.write(PROBES)
        builder.build(self.root)

    def add_locale(self, identity='zz-proof', formatting='ru-RU', direction='rtl'):
        folder = self.package / 'locales' / identity
        folder.mkdir()
        source = self.package / 'locales/en'
        for name in ('messages.ftl', 'prose.json', 'game.json'):
            shutil.copyfile(source / name, folder / name)
        info = {'schema': 1, 'id': identity, 'native_name': 'Synthetic 日本語 АБВ',
                'format_locale': formatting, 'direction': direction, 'aliases': ['zz-ZZ'],
                'fallback': None, 'enabled': True}
        write(folder / 'locale.json', info)
        data = builder.read(folder / 'prose.json')
        data['strings']['Sanctuaires'] = 'Proof 日本語 АБВ'
        write(folder / 'prose.json', data)
        path = folder / 'messages.ftl'
        tree = FluentParser().parse(path.read_text(encoding='utf-8'))
        replacement = FluentParser().parse('''renderitems-result = { $count ->
    [zero] { $value0 } synthetic zero
    [one] { $value0 } synthetic one
    [two] { $value0 } synthetic two
    [few] { $value0 } synthetic few
    [many] { $value0 } synthetic many
   *[other] { $value0 } synthetic other
    }
''').body[0]
        tree.body = [replacement if isinstance(item, ast.Message) and item.id.name == 'renderitems-result' else item for item in tree.body]
        path.write_text(FluentSerializer().serialize(tree), encoding='utf-8')
        return folder

    def test_resources_only_extension_reaches_html_api_and_launcher(self):
        before = fingerprint(self.root)
        folder = self.add_locale()
        builder.build(self.root)
        after = fingerprint(self.root)
        changed = {path for path in before if before[path] != after[path]}
        allowed = {'botw_companion/locales/registry.json',
                   *{f'botw_companion/locales/{locale}/{name}' for locale in ('fr', 'en') for name in ('index.html', 'browser.js')}}
        self.assertLessEqual(changed, allowed)
        self.assertEqual(set(p.name for p in folder.iterdir()), {'locale.json', 'messages.ftl', 'prose.json', 'game.json', 'presentation-data.json', 'contract.json', 'index.html', 'browser.js', 'browser.ftl', 'backend.ftl'})
        builder.build(self.root, check=True)
        with loaded(self.package):
            self.assertEqual(i18n.resolve('zz-ZZ'), 'zz-proof')
            self.assertIsNone(i18n.resolve('../../en'))
            document = i18n.locale_resource('index.html', 'zz-proof').read_text(encoding='utf-8')
            self.assertIn('<html lang="zz-proof" dir="rtl">', document)
            self.assertIn('html[dir="rtl"] #mapStage', document)
            self.assertIn('direction:ltr;unicode-bidi:isolate', document)
            self.assertIn('value="zz-proof"', document)
            self.assertIn('/locale.js?lang=zz-proof', document)
            expanded = builder.read(folder / 'presentation-data.json')['compiled_strings']
            self.assertEqual(len(expanded), len(builder.read(self.package / 'i18n/cache-source.json')))
            self.assertFalse((folder / 'legacy-cache.json').exists())
            self.assertEqual(expanded['Rejoindre le coffre - Rejoins X 3853.7, Z -1079.1.'],
                             'Join the chest - Go to X 3853.7, Z -1079.1.')
            data = Path(self.temporary.name) / 'synthetic-data'; data.mkdir()
            remember_language(data, 'zz-proof')
            self.assertEqual(saved_language(data), 'zz-proof')
            path = data / 'документ.log'
            self.assertIn(str(path), launcher_error(ValueError('JSON invalide'), path, known=True))
            self.assertIn('Invalid JSON', launcher_error(ValueError('JSON invalide'), path, known=True))
            handler, server = self.http_handler(data)
            for locale, text in [('fr', 'Sanctuaires'), ('en', 'Shrines'), ('zz-proof', 'Proof 日本語 АБВ')]:
                status, headers, body = self.request(handler, server, '/api/report?lang=' + locale)
                self.assertEqual(status, 200)
                self.assertEqual(headers['Content-Language'], locale)
                self.assertEqual(json.loads(body)['label'], text)
            self.assertEqual(self.request(handler, server, '/?lang=zz-proof')[0], 200)
            status, _, body = self.request(handler, server, '/api/language?lang=zz-proof', method='PUT', body=b'{bad')
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(body)['erreur'], 'Invalid JSON')
            for bad in ([], None, {}, True, '../../en', 'disabled', 'EN'):
                status, _, _ = self.request(handler, server, '/api/language?lang=en', method='PUT', body=json.dumps({'language': bad}).encode())
                self.assertEqual(status, 400)

    def http_handler(self, data):
        class Captured(Exception):
            pass
        class Server:
            server_port = 18765
            server_name = '127.0.0.1'
            def __init__(self, address, handler):
                self.handler = handler
                self.server_address = address
                captured.append(self)
                raise Captured()
        captured = []
        payload = {'label': 'Sanctuaires', 'categories': {}, 'elements': [], 'sauvegarde': {'slot': 1}}
        with patch('botw_companion.server.LoopbackThreadingHTTPServer', Server), self.assertRaises(Captured):
            serve(lambda: payload, open_browser=False,
                  tracking_store=ManualTrackingStore(data / 'manual.json'),
                  route_store=RouteSessionStore(data / 'routes.json'),
                  preference_store=PreferenceStore(data / 'preferences.json'),
                  runtime_state_store=RuntimeStateStore(data / 'runtime.json'),
                  instance_guard=MagicMock(), dsu_manager=MagicMock(),
                  update_checker=MagicMock(), update_download_manager=MagicMock(),
                  update_installer=MagicMock(), browser_handoff=MagicMock(), session_token='synthetic-token')
        return captured[0].handler, captured[0]

    @staticmethod
    def request(handler, server, path, headers=None, method='GET', body=b''):
        headers = {'Host': '127.0.0.1:18765', 'Connection': 'close', 'Content-Length': str(len(body)),
                   'Content-Type': 'application/json', 'X-BOTW-Session-Token': 'synthetic-token', **(headers or {})}
        raw = (f'{method} {path} HTTP/1.1\r\n' + ''.join(f'{k}: {v}\r\n' for k, v in headers.items()) + '\r\n').encode() + body
        output = io.BytesIO()
        class Connection:
            def makefile(self, *args):
                return io.BytesIO(raw)
            def sendall(self, value):
                output.write(value)
            def settimeout(self, _timeout):
                pass
        handler(Connection(), ('127.0.0.1', 1234), server)
        head, value = output.getvalue().split(b'\r\n\r\n', 1)
        lines = head.decode().split('\r\n')
        return int(lines[0].split()[1]), dict(line.split(': ', 1) for line in lines[1:]), value

    def test_selection_and_concurrency_preserve_parameters_and_personal_data(self):
        self.add_locale(); builder.build(self.root)
        with loaded(self.package):
            data = Path(self.temporary.name) / 'synthetic'; data.mkdir()
            handler, server = self.http_handler(data)
            for path, hints, expected in [('/api/report', {'Cookie': 'botw-language=en'}, 'en'),
                ('/api/report', {'Cookie': 'botw-language=en', 'X-BOTW-Language': 'fr'}, 'fr'),
                ('/api/report?lang=zz-proof', {'X-BOTW-Language': 'fr'}, 'zz-proof'),
                ('/api/report?lang=../../en', {'X-BOTW-Language': 'en'}, 'en'),
                ('/api/report?lang=invalid', {}, 'fr')]:
                self.assertEqual(self.request(handler, server, path, hints)[1]['Content-Language'], expected)
            original = {'label': 'Sanctuaires', 'note_personnelle': 'Sanctuaires', 'x': 12.5, 'z': -3,
                        'id': 'sanctuaires:Dungeon000', 'filename': 'Cocorico.json', 'status': 'termine'}
            frozen = copy.deepcopy(original)
            def render(index):
                locale = ['fr', 'en', 'zz-proof'][index % 3]
                value = presentation.present(original, locale)
                params = i18n.message('probe-values', locale, first=str(index), second='日本語')
                response = self.request(handler, server, '/api/report?lang=' + locale)
                return locale, value, params, response
            with ThreadPoolExecutor(max_workers=6) as pool:
                for index, (locale, value, params, response) in enumerate(pool.map(render, range(30))):
                    self.assertEqual(params, f'{index} / 日本語 / {index}')
                    self.assertEqual(response[1]['Content-Language'], locale)
                    self.assertEqual({k: v for k, v in value.items() if k != 'label'}, {k: v for k, v in original.items() if k != 'label'})
            self.assertEqual(original, frozen)
            self.assertEqual(presentation.present({'language': 'de', 'label': 'de'}, 'en'),
                             {'language': 'de', 'label': 'of'})
            device = {'name': 'Manette Cocorico — Arbre Mojo', 'id': 'device:example',
                      'path': '/tmp/Cocorico/device', 'gyro': True, 'kind': 'gamepad'}
            state = {'controllers': [device, {**device, 'name': 'Contrôleur inconnu'}],
                     'selected_source': 'device:1234:Cocorico', 'state_label': 'Désactivé'}
            rendered = presentation.present(state, 'en')
            self.assertEqual(rendered['controllers'][0], device)
            self.assertEqual(rendered['selected_source'], state['selected_source'])
            self.assertEqual(rendered['controllers'][1]['name'], presentation.translate_text('Contrôleur inconnu', 'en'))

    def test_same_python_js_cldr_and_safe_values_for_private_locales(self):
        outputs = {}
        for identity, formatting, direction in [('zz-proof', 'ru-RU', 'rtl'), ('zz-arabic', 'ar', 'rtl'), ('zz-cjk', 'zh-TW', 'ltr')]:
            folder = self.add_locale(identity, formatting, direction)
            info = builder.read(folder / 'locale.json'); info['aliases'] = []; write(folder / 'locale.json', info)
        builder.build(self.root)
        values = ["quotes ' \" { braces } % </script><img onerror=alert(1)>", 'line one\nline two 😀 العربية C:\\Cocorico\\' + '長' * 250]
        with loaded(self.package):
            for locale in ('fr', 'en', 'zz-proof', 'zz-arabic', 'zz-cjk'):
                outputs[locale] = {'count': [i18n.message('probe-count', locale, count=x) for x in COUNTS],
                                   'number': [i18n.message('probe-number', locale, count=x) for x in COUNTS],
                                   'actual': [i18n.message('renderitems-result', locale, value0=str(x), value1='s' if x > 1 else '', count=x) for x in COUNTS],
                                   'values': i18n.message('probe-values', locale, first=values[0], second=values[1])}
                self.assertEqual(outputs[locale]['values'], f'{values[0]} / {values[1]} / {values[0]}')
            self.assertEqual(set(outputs['zz-arabic']['count']), {'zero', 'one', 'two', 'few', 'many', 'other'})
            self.assertEqual(set(outputs['zz-cjk']['count']), {'other'})
        script = '''const fs=require('fs'),vm=require('vm');const config=JSON.parse(fs.readFileSync(0,'utf8'));const out={};
for(const locale of config.locales){const c=vm.createContext({});vm.runInContext(fs.readFileSync(config.package+'/locales/'+locale+'/browser.js','utf8'),c);vm.runInContext(fs.readFileSync(config.runtime,'utf8'),c);out[locale]={count:config.counts.map(count=>c.BOTWI18n.t('probe-count',{count})),number:config.counts.map(count=>c.BOTWI18n.t('probe-number',{count})),actual:config.counts.map(count=>c.BOTWI18n.t('renderitems-result',{value0:String(count),value1:count>1?'s':'',count})),values:c.BOTWI18n.t('probe-values',{first:config.values[0],second:config.values[1]})};
const rich=c.BOTWI18n.t('probe-rich',{open:'<b>',name:'&lt;/b&gt;&lt;script&gt;',close:'</b>'});if(rich!=='<b>&lt;img onerror=&quot;throw 1&quot;&gt;&lt;/b&gt;&lt;script&gt;</b>')throw Error('Unsafe rich content '+rich);
}process.stdout.write(JSON.stringify(out));'''
        result = subprocess.run(['node', '-e', script], input=json.dumps({'locales': list(outputs), 'counts': COUNTS, 'values': values, 'package': str(self.package), 'runtime': str(ROOT / 'botw_companion/web/i18n.js')}), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), outputs)

    def test_generation_is_idempotent_check_is_read_only_and_stale_is_rejected(self):
        before = fingerprint(self.root)
        builder.build(self.root)
        self.assertEqual(fingerprint(self.root), before)
        path = self.package / 'locales/en/browser.js'; path.write_text('stale', encoding='utf-8')
        stale = fingerprint(self.root)
        with self.assertRaisesRegex(ValueError, 'Stale'):
            builder.build(self.root, check=True)
        self.assertEqual(fingerprint(self.root), stale)

    def test_output_writers_preserve_utf8_lf_under_windows_text_translation(self):
        from tools import import_legacy_prose as importer

        native_open = Path.open

        def windows_open(path, mode='r', *args, **kwargs):
            if 'b' not in mode and any(flag in mode for flag in ('w', 'a')):
                if kwargs.get('newline') is None:
                    kwargs['newline'] = '\r\n'
            return native_open(path, mode, *args, **kwargs)

        before = fingerprint(self.root)
        with patch.object(Path, 'open', windows_open):
            probe = self.root / 'newline-probe.txt'
            probe.write_text('proof\n', encoding='utf-8')
            self.assertEqual(probe.read_bytes(), b'proof\r\n')
            probe.unlink()

            products = builder.build(self.root)
            for path, content in products:
                self.assertEqual(path.read_bytes(), content.encode('utf-8'), path)
                self.assertNotIn(b'\r\n', path.read_bytes(), path)
            with patch.object(Path, 'write_bytes', side_effect=AssertionError('Check must not write')):
                builder.build(self.root, check=True)
            builder.build(self.root)
            self.assertEqual(fingerprint(self.root), before)

            draft = builder.scaffold(self.root, 'zz-newline', 'Épreuve 日本語', 'en-US', 'ltr')
            for path in draft.iterdir():
                self.assertNotIn(b'\r\n', path.read_bytes(), path)
                path.read_bytes().decode('utf-8')
            self.assertEqual(builder.read(draft / 'locale.json')['native_name'], 'Épreuve 日本語')

            imported = self.root / 'imported'
            values = {'probe.ftl': 'probe = Épreuve 日本語\n',
                      'probe.json': {'label': 'Épreuve 日本語'}}
            with patch.object(importer, 'imported', return_value=values), patch('sys.argv', [
                'import_legacy_prose.py', '--source-data', str(self.root / 'legacy'),
                '--output', str(imported),
            ]):
                importer.main()
            self.assertEqual((imported / 'probe.ftl').read_bytes(), values['probe.ftl'].encode('utf-8'))
            self.assertEqual((imported / 'probe.json').read_bytes(),
                             (json.dumps(values['probe.json'], ensure_ascii=False, indent=2) + '\n').encode('utf-8'))

            path = self.package / 'locales/en/browser.js'
            path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
            stale = fingerprint(self.root)
            with patch.object(Path, 'write_bytes', side_effect=AssertionError('Check must not write')):
                with self.assertRaisesRegex(ValueError, 'Stale'):
                    builder.build(self.root, check=True)
            self.assertEqual(fingerprint(self.root), stale)

    def test_draft_missing_content_and_alias_fallback_schema_validation(self):
        folder = builder.scaffold(self.root, 'zz-draft', 'Draft', 'ru-RU', 'ltr')
        builder.build(self.root)
        self.assertNotIn('zz-draft', builder.read(self.package / 'locales/registry.json')['locales'])
        manifest = builder.read(folder / 'locale.json'); manifest['enabled'] = True; write(folder / 'locale.json', manifest)
        with self.assertRaisesRegex(ValueError, 'missing messages'):
            builder.build(self.root)
        shutil.rmtree(folder)
        folder = self.add_locale()
        original_text = (folder / 'locale.json').read_text(encoding='utf-8')
        (folder / 'locale.json').write_text(original_text.replace('"schema": 1', '"schema": 1, "schema": 1'), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
            builder.build(self.root)
        (folder / 'locale.json').write_text(original_text, encoding='utf-8')
        for change in ({'aliases': ['EN']}, {'id': 'en'}, {'fallback': 'zz-proof'}, {'unexpected': 1}, {'format_locale': '../en'}, {'direction': 'auto'}):
            original = builder.read(folder / 'locale.json'); write(folder / 'locale.json', {**original, **change})
            with self.assertRaises((ValueError, KeyError)):
                builder.build(self.root)
            write(folder / 'locale.json', original)
        prose = builder.read(folder / 'prose.json'); prose['strings'].pop('Sanctuaires'); write(folder / 'prose.json', prose)
        with self.assertRaisesRegex(ValueError, 'incomplete strings'):
            builder.build(self.root)

    def test_invalid_variables_markup_and_corrupt_runtime_are_bounded(self):
        with loaded(self.package):
            for values in ({}, {'first': 'a'}, {'first': 'a', 'second': []}, {'first': 'a', 'second': 'b', 'extra': 1}):
                with self.assertRaises(i18n.LocalizationError):
                    i18n.message('probe-values', 'en', **values)
            with self.assertRaises(i18n.LocalizationError):
                i18n.message('unknown-message', 'en')
            (self.package / 'locales/en/messages.ftl').unlink()
            (self.package / 'locales/en/backend.ftl').unlink()
            self.assertTrue(i18n.resource_errors())
            data = Path(self.temporary.name) / 'recovery'; data.mkdir()
            remember_language(data, 'en')
            i18n.catalog.cache_clear()
            self.assertIn('cannot', launcher_error(ValueError('bad'), data / 'x.log', known=True).lower().replace('ne peut pas', 'cannot'))
            self.assertNotIn('private unexpected detail', launcher_error(ValueError('private unexpected detail'), data / 'x.log', known=False))
            (data / 'presentation.json').write_text('{broken', encoding='utf-8')
            self.assertEqual(saved_language(data), 'fr')

    def test_catalog_parser_rejects_malformed_missing_variables_and_rich_slot_changes(self):
        path = self.package / 'locales/en/messages.ftl'
        original = path.read_text(encoding='utf-8')
        bad = [original + '\nprobe-count = duplicate\n',
               original.replace('probe-values = { $first } / { $second } / { $first }', 'probe-values = { $first }'),
               original.replace('probe-values = { $first }', 'probe-values = { $unexpected }'),
               original.replace('probe-rich = { $open }<img onerror="throw 1">{ $name }{ $close }', 'probe-rich = { $close }{ $name }{ $open }'),
               original + '\nbroken = {\n',
               original.replace('probe-number = { NUMBER($count, useGrouping: 0, maximumFractionDigits: 2) }', 'probe-number = { UNKNOWN($count) }'),
               original.replace('maximumFractionDigits: 2', 'maximumFractionDigits: "invalid"'),
               original.replace('maximumFractionDigits: 2', 'maximumFractionDigits: -1')]
        for text in bad:
            path.write_text(text, encoding='utf-8')
            with self.assertRaises(ValueError):
                builder.build(self.root)
        path.write_text(original, encoding='utf-8')

    def test_utf8_and_download_names_do_not_change_actual_paths(self):
        with loaded(self.package):
            data = Path(self.temporary.name) / 'invalid-language'; data.mkdir()
            for language in (None, [], {}, True, 'unknown', '../../en'):
                with self.assertRaises(ValueError):
                    remember_language(data, language)
            self.assertEqual(i18n.download_header('attachment; filename=botw-companion-itineraires.json', 'en'), 'attachment; filename=botw-companion-routes.json')
            for value in ('../private.json', 'bad\r\nX-Test: 1.json', 'C:\\private.json'):
                with patch.object(i18n, 'message', return_value=value), self.assertRaises(i18n.LocalizationError):
                    i18n.download_header('attachment; filename=botw-companion-itineraires.json', 'en')
            with patch.object(i18n, 'message', return_value='маршрут.json'):
                self.assertIn("filename*=UTF-8''%D0", i18n.download_header('attachment; filename=botw-companion-itineraires.json', 'en'))

    def test_corrupt_registry_fails_closed_without_navigation_or_path_selection(self):
        path = self.package / 'locales/registry.json'
        for value in ([], {}, {'schema': 1, 'locales': {}, 'aliases': {}, 'default': '../en'}):
            write(path, value)
            with loaded(self.package):
                self.assertIsNone(i18n.resolve('en'))
                self.assertEqual(i18n.default_locale(), 'und')
                self.assertTrue(i18n.resource_errors())
                data = Path(self.temporary.name)
                self.assertIn('BOTW Companion ne peut pas démarrer.', launcher_error(ValueError('Synthetic'), data / 'x.log', known=True))

    def test_generic_build_uses_utf8_with_restricted_default_streams_and_cyrillic_paths(self):
        import sys
        result = subprocess.run([sys.executable, '-X', 'utf8=0', str(ROOT / 'tools/i18n.py'), 'check', '--root', str(self.root)],
            env={**os.environ, 'PYTHONUTF8': '0', 'PYTHONIOENCODING': 'ascii', 'LC_ALL': 'C'}, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode('ascii', errors='replace'))


class LocalizationCheckoutTests(unittest.TestCase):
    def test_generated_resources_keep_lf_with_windows_checkout_filters(self):
        environment = {**os.environ, 'GIT_OPTIONAL_LOCKS': '0'}

        def git(*arguments):
            return subprocess.run(['git', '-c', 'core.autocrlf=true', *arguments],
                                  cwd=ROOT, env=environment, capture_output=True, check=True).stdout

        # Use an existing text blob without creating a repository or touching the index.
        source = 'HEAD:tools/i18n.py'
        original = git('cat-file', 'blob', source)
        self.assertIn(b'\n', original)
        self.assertNotIn(b'\r\n', original)
        for path, content in builder.outputs(ROOT):
            relative = path.relative_to(ROOT).as_posix()
            with self.subTest(resource=relative):
                checked_out = git('cat-file', '--filters', '--path=' + relative, source)
                self.assertEqual(checked_out, original)
                self.assertEqual(path.read_bytes(), content.encode('utf-8'))
