"""Regression tests for failure recovery and concurrent persistence."""
import json
import os
from pathlib import Path
import tempfile
import threading
import subprocess
import sys
import socket
import unittest
from unittest.mock import patch, Mock

from botw_companion.backup import CompanionBackup
from botw_companion.manual_tracking import ManualTrackingError, ManualTrackingStore
from botw_companion.preferences import PreferenceStore
from botw_companion.route_sessions import RouteSessionStore
from botw_companion.runtime_state import RuntimeStateStore
from botw_companion.windows_app import _server_arguments
from botw_companion.windows_launcher import server_command
from botw_companion.platforms import server_instance_guard
from botw_companion.persistence import atomic_write_json, copy_valid_backup, restore_bytes


class RecoveryAuditTests(unittest.TestCase):
    def test_concurrent_atomic_writers_publish_complete_json_without_shared_temps(self):
        path = self.root / 'concurrent.json'
        barrier = threading.Barrier(2)
        failures = []
        original_replace = os.replace
        rendezvous = threading.local()

        def replace(source, destination):
            # Only the first attempt must rendezvous: a retry belongs to the
            # same writer and must not wait for an already completed peer.
            if not getattr(rendezvous, 'arrived', False):
                rendezvous.arrived = True
                barrier.wait(3)
            original_replace(source, destination)

        def write(payload):
            try:
                atomic_write_json(path, payload)
            except Exception as exc:
                failures.append(exc)

        values = [{'writer': 1, 'note': 'A' * 10000}, {'writer': 2, 'note': 'B' * 10000}]
        with patch('botw_companion.persistence.os.replace', side_effect=replace):
            workers = [threading.Thread(target=write, args=(value,)) for value in values]
            for worker in workers: worker.start()
            for worker in workers: worker.join(4)
        self.assertFalse(any(worker.is_alive() for worker in workers))
        self.assertFalse(failures)
        self.assertIn(json.loads(path.read_text()), values)
        self.assertEqual(list(self.root.glob('*.tmp')), [])
        if os.name == 'posix':
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_windows_transient_replace_errors_retry_complete_data_in_all_writers(self):
        source, target = self.root / 'source.json', self.root / 'target.json'
        source.write_bytes(b'{"new": true}')
        operations = [
            lambda: atomic_write_json(target, {'new': True}),
            lambda: copy_valid_backup(source, target),
            lambda: restore_bytes(target, source.read_bytes()),
        ]
        original_replace = os.replace
        for code in (5, 32, 33):
            for index, operation in enumerate(operations):
                with self.subTest(code=code, operation=index):
                    target.write_bytes(b'{"old": true}')
                    error = PermissionError(13, 'Access is denied')
                    error.winerror = code
                    def replace(src, dst):
                        self.assertEqual(json.loads(target.read_bytes()), {'old': True})
                        self.assertEqual(json.loads(Path(src).read_bytes()), {'new': True})
                        if replace_mock.call_count <= 2:
                            raise error
                        original_replace(src, dst)
                    with patch('botw_companion.persistence._platform', 'win32'), \
                         patch('botw_companion.persistence.os.replace', side_effect=replace) as replace_mock, \
                         patch('botw_companion.persistence.time.sleep') as sleep_mock:
                        operation()
                    self.assertEqual(replace_mock.call_count, 3)
                    self.assertEqual(sleep_mock.call_count, 2)
                    self.assertEqual(json.loads(target.read_bytes()), {'new': True})
                    self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_permanent_replace_errors_preserve_old_data_and_have_bounded_retries(self):
        source, target = self.root / 'source.json', self.root / 'target.json'
        source.write_bytes(b'{"new": true}')
        operations = [
            lambda: atomic_write_json(target, {'new': True}),
            lambda: copy_valid_backup(source, target),
            lambda: restore_bytes(target, source.read_bytes()),
        ]
        for platform, code, attempts in [('win32', 5, 8), ('win32', 32, 8),
                                          ('win32', 33, 8), ('win32', 112, 1),
                                          ('win32', None, 1), ('darwin', 5, 1), ('linux', 32, 1)]:
            for index, operation in enumerate(operations):
                with self.subTest(platform=platform, code=code, operation=index):
                    target.write_bytes(b'{"old": true}')
                    error = OSError(13, 'cannot replace')
                    if code is not None:
                        error.winerror = code
                    with patch('botw_companion.persistence._platform', platform), \
                         patch('botw_companion.persistence.os.replace', side_effect=error) as replace_mock, \
                         patch('botw_companion.persistence.time.sleep') as sleep_mock:
                        with self.assertRaises(OSError) as caught:
                            operation()
                    self.assertIs(caught.exception, error)
                    self.assertEqual(replace_mock.call_count, attempts)
                    self.assertEqual(sleep_mock.call_count, attempts - 1)
                    self.assertLessEqual(sum(call.args[0] for call in sleep_mock.call_args_list), 0.5)
                    self.assertEqual(target.read_bytes(), b'{"old": true}')
                    self.assertEqual(list(self.root.glob('*.tmp')), [])

    @unittest.skipUnless(sys.platform == 'win32', 'Requires actual Windows file sharing semantics')
    def test_windows_reader_release_allows_atomic_publication(self):
        target = self.root / 'reader.json'
        target.write_bytes(b'{"old": true}')
        blocked = threading.Event()
        failures = []
        original_replace = os.replace
        def replace(src, dst):
            try:
                return original_replace(src, dst)
            except OSError:
                blocked.set()
                raise
        def write():
            try:
                atomic_write_json(target, {'new': True})
            except Exception as exc:
                failures.append(exc)
        with patch('botw_companion.persistence.os.replace', side_effect=replace):
            with target.open('rb') as reader:
                worker = threading.Thread(target=write)
                worker.start()
                observed = blocked.wait(2)
                self.assertEqual(reader.read(), b'{"old": true}')
            worker.join(2)
        self.assertTrue(observed, 'The native reader must actually block replacement')
        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(json.loads(target.read_bytes()), {'new': True})
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_invalid_utf8_primary_recovers_and_can_be_written_again(self):
        for cls in (ManualTrackingStore, RouteSessionStore, PreferenceStore, RuntimeStateStore):
            with self.subTest(store=cls.__name__):
                store = cls(self.root / (cls.__name__ + '.json'))
                valid = store._empty()
                store.backup_path.write_text(json.dumps(valid), encoding='utf-8')
                store.path.write_bytes(b'\xff\xfe damaged')
                self.assertEqual(store.load(), valid)
                if cls is ManualTrackingStore:
                    saved = store.update('test', True)
                elif cls is RouteSessionStore:
                    saved = store.replace(valid)
                elif cls is PreferenceStore:
                    saved = store.update({'sync_interval': 15})
                else:
                    saved = store.update_sync({'slot': '1'})
                self.assertEqual(store.load(), saved)
                self.assertEqual(json.loads(store.backup_path.read_text()), valid)

    def test_invalid_utf8_primary_and_backup_report_domain_error(self):
        for cls in (ManualTrackingStore, RouteSessionStore, PreferenceStore, RuntimeStateStore):
            with self.subTest(store=cls.__name__):
                store = cls(self.root / (cls.__name__ + '.json'))
                store.path.write_bytes(b'\xff')
                store.backup_path.write_bytes(b'\xff')
                with self.assertRaises(ManualTrackingError):
                    store.load()

    def test_unhashable_preference_values_are_rejected_without_mutation(self):
        store = PreferenceStore(self.root / 'preferences.json')
        original = store.update({'sync_interval': 15})
        for value in ([], {}, ['base']):
            with self.subTest(value=value), self.assertRaises(ManualTrackingError):
                store.update({'map_content_mode': value})
        self.assertEqual(store.load(), original)

    def test_unhashable_preference_on_disk_recovers_backup(self):
        store = PreferenceStore(self.root / 'preferences.json')
        original = store.update({'sync_interval': 15})
        store.update({'sync_interval': 30})
        store.path.write_text(json.dumps({**original, 'values': {'sync_interval': []}}))
        self.assertEqual(store.load(), original)

    def test_route_coordinates_are_finite_in_every_import_path(self):
        store = RouteSessionStore(self.root / 'routes.json')
        for value in (float('nan'), float('inf'), float('-inf'), 'NaN', 'Infinity', 10**400):
            for field in ('start', 'snapshot'):
                with self.subTest(value=str(value), field=field), self.assertRaises(ManualTrackingError):
                    session = {'name': 'test', 'entries': []}
                    if field == 'start':
                        session['start'] = {'x': value, 'z': 0}
                    else:
                        session['entries'] = [{'tracking_id': 'test', 'snapshot': {'x': value, 'z': 0}}]
                    store.import_session(session)
        self.assertFalse(store.path.exists())

    def test_malformed_route_structures_are_domain_errors(self):
        store = RouteSessionStore(self.root / 'routes.json')
        for session in ({'strategy': []}, {'strategy': {}}, {'steps': [None]}, {'steps': [42]}):
            with self.subTest(session=session), self.assertRaises(ManualTrackingError):
                store.import_session(session)
        candidate = store._empty()
        candidate['active_session_id'] = []
        with self.assertRaises(ManualTrackingError):
            store.replace(candidate)
        candidate = store._empty()
        candidate['sessions'][candidate['active_session_id']]['id'] = 'different-id'
        with self.assertRaises(ManualTrackingError):
            store.replace(candidate)
        self.assertFalse(store.path.exists())

    def test_malformed_import_mode_and_backup_version_are_domain_errors(self):
        manual = ManualTrackingStore(self.root / 'manual.json')
        backup = CompanionBackup(manual, RouteSessionStore(self.root / 'routes.json'),
                                 PreferenceStore(self.root / 'preferences.json'))
        for value in ([], {}):
            with self.subTest(mode=value), self.assertRaises(ManualTrackingError):
                manual.import_data(manual._empty(), mode=value)
            payload = backup.export()
            payload['schema_version'] = value
            with self.subTest(version=value), self.assertRaises(ManualTrackingError):
                backup.restore(payload)


class BackupTransactionAuditTests(unittest.TestCase):
    def test_failed_rollback_keeps_journal_until_retry_can_restore_every_file(self):
        from botw_companion.persistence import restore_bytes
        originals = {path: path.read_bytes() for path in self.backup._paths()}
        payload = self.backup.export()
        payload['manual_tracking']['entries'] = {'imported': {'completed': True}}

        def fail_once(path, content):
            if path == self.routes.path:
                raise OSError('device unavailable during rollback')
            restore_bytes(path, content)

        with patch.object(self.preferences, 'replace', side_effect=OSError('disk full')):
            with patch('botw_companion.backup.restore_bytes', side_effect=fail_once):
                with self.assertRaises(OSError):
                    self.backup.restore(payload)
        self.assertTrue(self.backup.journal_path.exists())
        self.backup.recover_pending()
        for path, content in originals.items():
            self.assertEqual(path.read_bytes(), content, str(path))
        self.assertFalse(self.backup.journal_path.exists())

    def test_forced_process_exit_mid_restore_recovers_every_file_on_next_start(self):
        originals = {path: path.read_bytes() for path in self.backup._paths()}
        payload = self.backup.export()
        payload['manual_tracking']['entries'] = {'imported': {'completed': True}}
        payload_path = self.manual.path.parent / 'incoming.json'
        payload_path.write_text(json.dumps(payload), encoding='utf-8')
        script = '''import json, os, sys
from pathlib import Path
from botw_companion.backup import CompanionBackup
from botw_companion.manual_tracking import ManualTrackingStore
from botw_companion.route_sessions import RouteSessionStore
from botw_companion.preferences import PreferenceStore
root=Path(sys.argv[1])
preferences=PreferenceStore(root/'preferences.json')
preferences.replace=lambda *args: os._exit(42)
backup=CompanionBackup(ManualTrackingStore(root/'manual.json'),RouteSessionStore(root/'routes.json'),preferences)
backup.restore(json.loads((root/'incoming.json').read_text(encoding='utf-8')))
'''
        result = subprocess.run([sys.executable, '-B', '-c', script, str(self.manual.path.parent)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 42, result.stdout + result.stderr)
        self.assertTrue(self.backup.journal_path.exists())
        self.assertIn('imported', json.loads(self.manual.path.read_text())['entries'])
        self.backup.recover_pending()
        for path, content in originals.items():
            self.assertEqual(path.read_bytes(), content, str(path))
        self.assertFalse(self.backup.journal_path.exists())
        self.backup.restore(payload)
        self.assertIn('imported', self.manual.load()['entries'])
        self.assertFalse(self.backup.journal_path.exists())

    def test_invalid_journal_never_controls_destinations_or_overwrites_data(self):
        originals = {path: path.read_bytes() for path in self.backup._paths()}
        journal = {'schema_version': 1, 'paths': ['/foreign/path'] * 6, 'contents': [None] * 6}
        self.backup.journal_path.write_text(json.dumps(journal))
        with self.assertRaises(ManualTrackingError):
            self.backup.recover_pending()
        self.assertEqual(json.loads(self.backup.journal_path.read_text()), journal)
        for path, content in originals.items():
            self.assertEqual(path.read_bytes(), content)

    def test_export_locks_every_store_before_reading_any_of_them(self):
        acquired = []
        original_load = self.manual.load

        def concurrent_probe():
            for store in (self.manual, self.routes, self.preferences):
                success = store._lock.acquire(blocking=False)
                acquired.append(success)
                if success: store._lock.release()

        def load():
            other = threading.Thread(target=concurrent_probe)
            other.start(); other.join(2)
            return original_load()

        with patch.object(self.manual, 'load', side_effect=load):
            self.backup.export()
        self.assertEqual(acquired, [False, False, False])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.manual = ManualTrackingStore(root / 'manual.json')
        self.routes = RouteSessionStore(root / 'routes.json')
        self.preferences = PreferenceStore(root / 'preferences.json')
        self.backup = CompanionBackup(self.manual, self.routes, self.preferences)
        self.manual.update('original', True)
        self.manual.update('second', True)
        self.routes.replace(self.routes.load())
        self.routes.replace(self.routes.load())
        self.preferences.update({'sync_interval': 15})
        self.preferences.update({'sync_interval': 30})

    def tearDown(self):
        self.temporary.cleanup()

    def test_restore_failure_rolls_back_primary_and_recovery_files(self):
        originals = {path: path.read_bytes() for store in (self.manual, self.routes, self.preferences)
                     for path in (store.path, store.backup_path)}
        payload = self.backup.export()
        payload['manual_tracking']['entries'] = {'imported': {'completed': True}}
        with patch.object(self.preferences, 'replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.backup.restore(payload)
        for path, content in originals.items():
            self.assertEqual(path.read_bytes(), content, str(path))

    def test_restore_does_not_erase_a_concurrent_tab_write_on_failure(self):
        entered, release, writer_started, writer_done = (threading.Event() for _ in range(4))
        failures = []
        payload = self.backup.export()

        def fail_preferences(*args):
            entered.set()
            if not release.wait(3):
                raise RuntimeError('test barrier timeout')
            raise OSError('disk full')

        def restore():
            try:
                self.backup.restore(payload)
            except OSError:
                pass
            except Exception as exc:
                failures.append(exc)

        def write():
            writer_started.set()
            try:
                self.manual.update('concurrent', True)
            except Exception as exc:
                failures.append(exc)
            finally:
                writer_done.set()

        with patch.object(self.preferences, 'replace', side_effect=fail_preferences):
            restoring = threading.Thread(target=restore)
            writing = threading.Thread(target=write)
            restoring.start()
            try:
                self.assertTrue(entered.wait(3))
                writing.start()
                self.assertTrue(writer_started.wait(3))
                self.assertFalse(writer_done.wait(.15), 'A tab wrote inside the restore transaction')
            finally:
                release.set()
                restoring.join(3)
                if writing.ident:
                    writing.join(3)
        self.assertFalse(restoring.is_alive())
        self.assertFalse(writing.is_alive())
        self.assertFalse(failures)
        self.assertTrue(self.manual.load()['entries']['concurrent']['completed'])


class ProcessDetectionAuditTests(unittest.TestCase):
    def test_cli_selected_emulator_watcher_uses_the_strict_detection_path(self):
        from botw_companion import cli
        sync = Mock()
        sync.source_emulator.return_value = 'cemu'

        def serve(*args, **kwargs):
            self.assertTrue(kwargs['monitor_emulator'])
            with self.assertRaises(OSError):
                kwargs['emulator_running']()

        with patch.object(cli, 'ReliableSaveSync', return_value=sync), patch.object(cli, 'serve', side_effect=serve):
            with patch.object(cli, 'reliable_running_emulators', side_effect=OSError('snapshot unavailable')) as detector:
                self.assertEqual(cli.main(['interface', '--sans-navigateur', '--arreter-avec-emulateur']), 0)
        detector.assert_called_once_with()

    def test_macos_snapshot_error_is_distinct_from_no_emulator(self):
        from botw_companion.emulators import reliable_emulator_running
        from botw_companion.platforms import macos
        for failure in (OSError('ps unavailable'), subprocess.TimeoutExpired('ps', 2)):
            with self.subTest(failure=failure), patch.object(macos.subprocess, 'run', side_effect=failure):
                self.assertEqual(macos.process_names(), set())
                with self.assertRaises(OSError):
                    reliable_emulator_running(system='Darwin')
        with patch.object(macos.subprocess, 'run', return_value=Mock(returncode=1, stdout='')):
            with self.assertRaises(OSError):
                reliable_emulator_running(system='Darwin')

    def test_windows_snapshot_failure_is_distinct_from_no_emulator(self):
        from botw_companion.platforms import windows
        kernel = Mock()
        kernel.CreateToolhelp32Snapshot.return_value = windows.INVALID_HANDLE_VALUE
        self.assertEqual(windows.running_process_names(kernel32=kernel), set())
        with self.assertRaises(OSError):
            windows.running_process_names(kernel32=kernel, strict=True)
        kernel.CloseHandle.assert_not_called()

    def test_failed_windows_enumeration_still_releases_handle(self):
        from botw_companion.platforms import windows
        kernel = Mock()
        kernel.CreateToolhelp32Snapshot.return_value = 99
        kernel.Process32FirstW.return_value = False
        with patch.object(windows.ctypes, 'get_last_error', return_value=5, create=True):
            with self.assertRaises(OSError):
                windows.running_process_names(kernel32=kernel, strict=True)
        kernel.CloseHandle.assert_called_once_with(99)

    def test_detection_error_cannot_trigger_automatic_shutdown(self):
        from botw_companion.emulators import reliable_emulator_running
        from botw_companion.lifecycle import EmulatorLifecycleWatcher
        from botw_companion.platforms import macos
        now = [0]
        shutdown = Mock()
        detector = lambda: reliable_emulator_running(system='Darwin')
        watcher = EmulatorLifecycleWatcher(detector, shutdown, clock=lambda: now[0])
        with patch.object(macos.subprocess, 'run', return_value=Mock(returncode=0, stdout='/Applications/Cemu')):
            self.assertFalse(watcher.check_once())
        with patch.object(macos.subprocess, 'run', side_effect=OSError('process query failed')):
            for timestamp in (15, 30, 45, 60, 75, 90):
                now[0] = timestamp
                self.assertFalse(watcher.check_once())
        self.assertEqual(watcher.status()['state'], 'erreur_detection')
        self.assertIsNone(watcher.status()['missing_since'])
        shutdown.assert_not_called()
        with patch.object(macos.subprocess, 'run', return_value=Mock(returncode=0, stdout='/Applications/Cemu')):
            now[0] = 105
            self.assertFalse(watcher.check_once())
        self.assertEqual(watcher.status()['state'], 'emulateur_actif')


class PackagedLauncherAuditTests(unittest.TestCase):
    def test_server_startup_and_cleanup_errors_release_socket_and_guard(self):
        from botw_companion.server import serve
        for failing_stage in ('notifier', 'ready', 'child-close'):
            with self.subTest(stage=failing_stage):
                guard = Mock()
                guard.acquire.return_value = True
                download, dsu, notifier = Mock(), Mock(), Mock()
                ports = []

                def ready(port):
                    ports.append(port)
                    raise RuntimeError('startup interrupted')

                def make_notifier(callback):
                    if failing_stage == 'notifier':
                        raise RuntimeError('native notifier failed')
                    return notifier

                if failing_stage == 'child-close':
                    dsu.close.side_effect = OSError('child cannot stop')
                with self.assertRaises((RuntimeError, OSError)):
                    serve(lambda: {}, port=0, open_browser=False, instance_guard=guard,
                          shutdown_notifier_factory=make_notifier, server_ready=ready,
                          dsu_manager=dsu, update_download_manager=download)
                guard.close.assert_called_once_with()
                download.close.assert_called_once_with()
                dsu.close.assert_called_once_with()
                if ports:
                    with socket.socket() as listener:
                        if os.name != 'nt': listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        listener.bind(('127.0.0.1', ports[0]))

    def test_both_launchers_accept_an_update_port_override(self):
        from botw_companion import macos_launcher, windows_launcher
        for launcher in (macos_launcher, windows_launcher):
            with self.subTest(launcher=launcher.__name__), tempfile.TemporaryDirectory() as directory:
                with patch.object(launcher, 'run', return_value=0) as run, \
                     patch.object(launcher, 'companion_data_dir', return_value=Path(directory)):
                    self.assertEqual(launcher.main(['--port', '9876']), 0)
                self.assertEqual(run.call_args.kwargs['port_override'], 9876)

    def test_launcher_logging_closes_its_file_on_success_and_error(self):
        import logging
        from botw_companion import macos_launcher, windows_launcher
        for launcher in (macos_launcher, windows_launcher):
            for fail in (False, True):
                with self.subTest(launcher=launcher.__name__, fail=fail), tempfile.TemporaryDirectory() as directory:
                    logger = logging.getLogger(launcher.__name__)
                    root = logging.getLogger()
                    before = (list(logger.handlers), logger.level, logger.propagate, list(root.handlers), root.level)
                    created = []
                    original = logging.FileHandler
                    def create_handler(*args, **kwargs):
                        result = original(*args, **kwargs)
                        created.append(result)
                        return result
                    with patch.object(launcher, 'run', side_effect=launcher.LauncherError('Le port configuré doit être compris entre 1 et 65535') if fail else None, return_value=0), \
                         patch.object(launcher, 'companion_data_dir', return_value=Path(directory)), \
                         patch.object(launcher, 'show_error') as show, \
                         patch('botw_companion.launcher_support.logging.FileHandler', side_effect=create_handler):
                        self.assertEqual(launcher.main([]), int(fail))
                    # Check the actual owned stream, not only POSIX unlink behavior.
                    self.assertEqual(len(created), 1)
                    self.assertIsNone(created[0].stream)
                    self.assertEqual((list(logger.handlers), logger.level, logger.propagate, list(root.handlers), root.level), before)
                    log = Path(directory) / 'launcher.log'
                    text = log.read_text(encoding='utf-8')
                    self.assertIn('Lancement de BOTW Companion', text)
                    if fail:
                        self.assertIn('Échec du lanceur', text)
                        show.assert_called_once()
                    # Windows rejects this operation when an owned handle leaked.
                    log.rename(Path(directory) / 'closed.log')

    def test_native_error_uses_saved_language_and_preserves_the_log_path(self):
        from botw_companion.launcher_support import launcher_error, remember_language
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Cocorico Elimith' / 'launcher.log'
            error = RuntimeError('Le port configuré doit être compris entre 1 et 65535')
            for language, expected in (('en', 'BOTW Companion cannot start.'), ('fr', 'BOTW Companion ne peut pas démarrer.')):
                remember_language(path.parent, language)
                message = launcher_error(error, path, known=True)
                self.assertTrue(message.startswith(expected))
                self.assertIn(str(path), message)
                if language == 'en':
                    self.assertNotIn('Le port configuré', message)
                unknown = launcher_error(OSError('Raw operating system diagnostics'), path, known=False)
                self.assertNotIn('Raw operating system diagnostics', unknown)
            (path.parent / 'presentation.json').write_bytes(b'\xff')
            self.assertIn('ne peut pas démarrer', launcher_error(error, path, known=True))

    def test_windows_frozen_launcher_command_is_accepted_by_the_entry_point(self):
        command = server_command(Path('BOTW Companion.exe'), Path('.'), 8765,
                                 {'save_path': 'D:/Zelda saves'}, frozen=True)
        mapped = _server_arguments(command[1:])
        self.assertEqual(mapped[0:2], ['interface', 'D:/Zelda saves'])
        self.assertIn('--sans-navigateur', mapped)
        self.assertIn('--arreter-avec-ryujinx', mapped)


@unittest.skipUnless(os.name == 'posix', 'POSIX locks require a native POSIX host')
class PosixInstanceAuditTests(unittest.TestCase):
    def test_shared_data_directory_remains_exclusive_and_a_crash_releases_it(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = {**os.environ, 'BOTW_COMPANION_DATA_DIR': directory}
            guard = server_instance_guard(system='Linux', environ=environment)
            script = "from botw_companion.platforms import server_instance_guard; import time; g=server_instance_guard(); print(g.acquire(), flush=True); time.sleep(30)"
            process = subprocess.Popen([sys.executable, '-B', '-c', script], env=environment,
                                       stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(process.stdout.readline().strip(), 'True')
                self.assertFalse(guard.acquire())
            finally:
                process.kill(); process.wait(3); process.stdout.close()
            try:
                self.assertTrue(guard.acquire())
                other = server_instance_guard(system='Linux', environ=environment)
                self.assertFalse(other.acquire())
                guard.close()
                self.assertTrue(other.acquire())
                other.close()
            finally:
                guard.close()


if __name__ == '__main__':
    unittest.main()
