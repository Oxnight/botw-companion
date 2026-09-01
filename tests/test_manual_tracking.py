import json
from pathlib import Path
import tempfile
import unittest

from botw_companion.manual_tracking import ManualTrackingError, ManualTrackingStore


class ManualTrackingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "manual.json"
        self.store = ManualTrackingStore(self.path)

    def tearDown(self):
        self.temporary.cleanup()

    def test_checkbox_and_note_survive_a_new_store_instance(self):
        saved = self.store.update("sanctuaires:Dungeon000", True, "Coffre vérifié", 0)
        restored = ManualTrackingStore(self.path).load()
        self.assertEqual(saved, restored)
        self.assertEqual(restored["revision"], 1)
        self.assertTrue(restored["entries"]["sanctuaires:Dungeon000"]["completed"])
        self.assertEqual(restored["entries"]["sanctuaires:Dungeon000"]["note"], "Coffre vérifié")

    def test_unchecking_without_a_note_removes_the_entry(self):
        first = self.store.update("lieux:Location_Test", True, expected_revision=0)
        second = self.store.update("lieux:Location_Test", False, expected_revision=first["revision"])
        self.assertEqual(second["entries"], {})

    def test_unchecking_from_review_keeps_the_personal_note(self):
        first = self.store.update("korogus:one", True, "Sous le rocher", 0)
        second = self.store.update(
            "korogus:one",
            False,
            "Sous le rocher",
            first["revision"],
        )
        entry = second["entries"]["korogus:one"]
        self.assertFalse(entry["completed"])
        self.assertEqual(entry["note"], "Sous le rocher")

    def test_stale_browser_revision_cannot_overwrite_newer_data(self):
        self.store.update("korogus:one", True, expected_revision=0)
        with self.assertRaises(ManualTrackingError):
            self.store.update("korogus:two", True, expected_revision=0)

    def test_import_merges_without_erasing_existing_checks(self):
        current = self.store.update("korogus:one", True, expected_revision=0)
        imported = {"schema_version": 1, "revision": 9, "entries": {
            "quetes_secondaires:two": {"completed": True, "note": "fait"},
        }}
        result = self.store.import_data(imported, expected_revision=current["revision"])
        self.assertEqual(set(result["entries"]), {"korogus:one", "quetes_secondaires:two"})

    def test_valid_backup_is_used_when_primary_file_is_corrupted(self):
        first = self.store.update("korogus:one", True, expected_revision=0)
        self.store.update("korogus:two", True, expected_revision=first["revision"])
        self.path.write_text("{cassé", encoding="utf-8")
        recovered = self.store.load()
        self.assertIn("korogus:one", recovered["entries"])
        self.assertNotIn("korogus:two", recovered["entries"])

    def test_invalid_import_is_rejected_without_touching_disk(self):
        before = self.store.update("korogus:one", True, expected_revision=0)
        with self.assertRaises(ManualTrackingError):
            self.store.import_data({"entries": {"bad": {"completed": "yes"}}},
                                   expected_revision=before["revision"])
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["revision"], 1)


if __name__ == "__main__":
    unittest.main()