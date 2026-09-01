import json
from pathlib import Path
import tempfile
import unittest

from botw_companion.manual_tracking import ManualTrackingError
from botw_companion.route_sessions import RouteSessionStore


class RouteSessionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = RouteSessionStore(Path(self.temp.name) / "routes.json")

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def populated(store):
        data = store.load()
        session = data["sessions"][data["active_session_id"]]
        session.update(name="Farm Lynels", strategy="region", entries=[
            {"tracking_id": "lynel:a", "locked": True,
             "snapshot": {"name": "Lynel rouge", "region": "Plaine", "x": 10, "z": 20}},
        ])
        return data

    def test_named_sessions_survive_a_new_store_instance(self):
        saved = self.store.replace(self.populated(self.store), 0)
        loaded = RouteSessionStore(self.store.path).load()
        self.assertEqual(loaded, saved)
        session = loaded["sessions"][loaded["active_session_id"]]
        self.assertEqual((session["name"], session["strategy"]), ("Farm Lynels", "region"))

    def test_stale_window_cannot_overwrite_routes(self):
        first = self.store.replace(self.populated(self.store), 0)
        with self.assertRaisesRegex(ManualTrackingError, "autre fenêtre"):
            self.store.replace(first, 0)

    def test_legacy_export_import_preserves_order_locks_and_snapshots(self):
        exported = {"schema_version": 1, "name": "Ancienne route", "start": {"x": 1, "z": 2, "label": "Départ"},
                    "steps": [{"tracking_id": "a", "name": "A", "region": "Firone", "x": 3, "z": 4, "locked": False},
                              {"tracking_id": "missing", "name": "Ancien objectif", "region": "DLC", "x": 5, "z": 6, "locked": True}]}
        result = self.store.import_session(exported, 0)
        session = result["sessions"][result["active_session_id"]]
        self.assertEqual([entry["tracking_id"] for entry in session["entries"]], ["a", "missing"])
        self.assertTrue(session["entries"][1]["locked"])
        self.assertEqual(session["entries"][1]["snapshot"]["name"], "Ancien objectif")

    def test_corrupted_primary_uses_backup(self):
        first = self.store.replace(self.populated(self.store), 0)
        second = self.store.replace(first, first["revision"])
        self.store.path.write_text("{", encoding="utf-8")
        self.assertEqual(self.store.load()["revision"], first["revision"])

    def test_duplicate_steps_and_oversized_names_are_rejected(self):
        data = self.populated(self.store)
        session = data["sessions"][data["active_session_id"]]
        session["entries"].append(dict(session["entries"][0]))
        with self.assertRaises(ManualTrackingError):
            self.store.replace(data, 0)

    def test_a_session_accepts_one_thousand_steps_but_not_more(self):
        data = self.store.load()
        session = data["sessions"][data["active_session_id"]]
        session["entries"] = [{"tracking_id": f"point:{index}", "snapshot": {}}
                              for index in range(1000)]
        saved = self.store.replace(data, 0)
        self.assertEqual(len(saved["sessions"][saved["active_session_id"]]["entries"]), 1000)
        saved["sessions"][saved["active_session_id"]]["entries"].append(
            {"tracking_id": "point:1000", "snapshot": {}}
        )
        with self.assertRaisesRegex(ManualTrackingError, "1000 étapes"):
            self.store.replace(saved, saved["revision"])


if __name__ == "__main__":
    unittest.main()