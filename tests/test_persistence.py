import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from botw_companion.backup import CompanionBackup
from botw_companion.manual_tracking import ManualTrackingError, ManualTrackingStore
from botw_companion.preferences import PreferenceStore
from botw_companion.route_sessions import RouteSessionStore
from botw_companion.runtime_state import RuntimeStateStore


class PersistentMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_manual_schema_one_is_migrated_atomically_and_preserved(self):
        path = self.root / "manual_tracking.json"
        legacy = {
            "schema_version": 1,
            "revision": 7,
            "updated_at": "2025-01-01T00:00:00+00:00",
            "entries": {"korogus:a": {"completed": True, "note": "fait"}},
        }
        path.write_text(json.dumps(legacy), encoding="utf-8")
        loaded = ManualTrackingStore(path).load()
        self.assertEqual(loaded["schema_version"], 2)
        self.assertEqual(loaded["revision"], 7)
        self.assertTrue(loaded["entries"]["korogus:a"]["completed"])
        migration = path.with_name("manual_tracking.pre-migration-v1.json")
        self.assertEqual(json.loads(migration.read_text(encoding="utf-8")), legacy)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema_version"], 2)

    def test_route_schema_one_becomes_a_named_session_without_losing_order(self):
        path = self.root / "route_sessions.json"
        legacy = {
            "schema_version": 1,
            "revision": 4,
            "name": "Ancienne session",
            "strategy": "region",
            "steps": [
                {"tracking_id": "a", "name": "A", "x": 1, "z": 2},
                {"tracking_id": "b", "name": "B", "x": 3, "z": 4, "locked": True},
            ],
        }
        path.write_text(json.dumps(legacy), encoding="utf-8")
        loaded = RouteSessionStore(path).load()
        self.assertEqual(loaded["schema_version"], 3)
        session = loaded["sessions"][loaded["active_session_id"]]
        self.assertEqual(session["name"], "Ancienne session")
        self.assertEqual([entry["tracking_id"] for entry in session["entries"]], ["a", "b"])
        self.assertTrue(session["entries"][1]["locked"])
        self.assertTrue(path.with_name("route_sessions.pre-migration-v1.json").exists())

    def test_future_schemas_are_rejected_without_modifying_the_file(self):
        path = self.root / "manual_tracking.json"
        original = '{"schema_version":999,"entries":{}}'
        path.write_text(original, encoding="utf-8")
        with self.assertRaisesRegex(ManualTrackingError, "non prise en charge"):
            ManualTrackingStore(path).load()
        self.assertEqual(path.read_text(encoding="utf-8"), original)


class PreferenceStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "preferences.json"
        self.store = PreferenceStore(self.path)

    def tearDown(self):
        self.temporary.cleanup()

    def test_preferences_survive_a_new_store_and_have_no_platform_path(self):
        saved = self.store.update({
            "sync_interval": 15,
            "map_content_mode": "dlc",
            "completion_profile": "expert",
            "game_mode_filter": "save",
            "dsu_mode": "integrated",
        }, 0)
        restored = PreferenceStore(self.path).load()
        self.assertEqual(restored, saved)
        serialized = json.dumps(restored)
        self.assertNotIn("/Users/", serialized)
        self.assertNotIn("C:\\\\", serialized)

    def test_invalid_preference_is_rejected_without_touching_disk(self):
        before = self.store.update({"sync_interval": 30}, 0)
        with self.assertRaisesRegex(ManualTrackingError, "Préférence invalide"):
            self.store.update({"sync_interval": 1}, before["revision"])
        self.assertEqual(self.store.load(), before)

    def test_corrupted_primary_uses_the_last_valid_backup(self):
        first = self.store.update({"sync_interval": 15}, 0)
        self.store.update({"map_content_mode": "base"}, first["revision"])
        self.path.write_text("{", encoding="utf-8")
        recovered = self.store.load()
        self.assertEqual(recovered["values"], {"sync_interval": 15})

    def test_unicode_windows_style_user_directory_preserves_content(self):
        path = self.path.parent / "Données Zelda 漢字" / "preferences.json"
        store = PreferenceStore(path)
        saved = store.update({"completion_profile": "dlc", "dsu_mode": "external"}, 0)
        self.assertEqual(PreferenceStore(path).load(), saved)
        self.assertIn("Données Zelda 漢字", str(path))


class CompleteBackupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.manual = ManualTrackingStore(root / "manual.json")
        self.routes = RouteSessionStore(root / "routes.json")
        self.preferences = PreferenceStore(root / "preferences.json")
        self.backup = CompanionBackup(self.manual, self.routes, self.preferences)

    def tearDown(self):
        self.temporary.cleanup()

    def _populate(self):
        self.manual.update("korogus:a", True, expected_revision=0)
        routes = self.routes.load()
        session = routes["sessions"][routes["active_session_id"]]
        session["entries"] = [{"tracking_id": "korogus:a", "snapshot": {"name": "Korogu"}}]
        self.routes.replace(routes, 0)
        self.preferences.update({"map_content_mode": "dlc", "sync_interval": 15}, 0)

    def test_export_and_restore_preserve_all_portable_user_data(self):
        self._populate()
        exported = self.backup.export()
        self.manual.update("korogus:a", False, expected_revision=1)
        self.preferences.update({"map_content_mode": "base"}, 1)
        restored = self.backup.restore(exported)
        self.assertTrue(restored["manual_tracking"]["entries"]["korogus:a"]["completed"])
        self.assertEqual(restored["preferences"]["values"]["map_content_mode"], "dlc")
        serialized = json.dumps(exported)
        self.assertNotIn("/Users/", serialized)
        self.assertNotIn("AppData", serialized)
        self.assertNotIn("runtime_state", exported)

    def test_schema_one_backup_without_preferences_still_restores(self):
        self._populate()
        exported = self.backup.export()
        exported["schema_version"] = 1
        del exported["preferences"]
        restored = self.backup.restore(exported)
        self.assertEqual(restored["preferences"]["values"], {})

    def test_failure_rolls_back_every_primary_file(self):
        self._populate()
        exported = self.backup.export()
        originals = {
            store.path: store.path.read_bytes()
            for store in (self.manual, self.routes, self.preferences)
        }
        with patch.object(self.preferences, "replace", side_effect=OSError("disque plein")):
            with self.assertRaisesRegex(OSError, "disque plein"):
                self.backup.restore(exported)
        for path, content in originals.items():
            self.assertEqual(path.read_bytes(), content)


class RuntimeStateTests(unittest.TestCase):
    def test_local_source_and_history_are_versioned_but_never_rewritten_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RuntimeStateStore(Path(directory) / "runtime_state.json")
            synchronization = {
                "source_root": "/Users/link/Ryujinx/save",
                "slot": "1",
                "save_mode": "normal",
                "save_timestamp": 1234,
                "source_kind": "standard",
                "events": [{"at": "maintenant", "kind": "succes", "message": "À jour"}],
            }
            first = store.update_sync(synchronization)
            with patch("botw_companion.runtime_state.atomic_write_json") as writer:
                second = store.update_sync(synchronization)
            writer.assert_not_called()
            self.assertEqual(second, first)
            self.assertEqual(second["schema_version"], 1)
            self.assertEqual(second["last_save_source"], "/Users/link/Ryujinx/save")


if __name__ == "__main__":
    unittest.main()