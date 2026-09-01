import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from botw_companion.save import parse_file as real_parse_file
from botw_companion.synchronization import ReliableSaveSync, SaveSnapshot


HASH = 195546944


def fake_file(path: Path, timestamp: int) -> None:
    marker = b"\x00\x00\x00\x01\xff\xff\xff\xff\x00\x00\x00\x01"
    path.write_bytes(marker + struct.pack(">Ii", HASH, timestamp) + b"\xff\xff\xff\xff")


def fake_slot(root: Path, name: str, timestamp: int) -> Path:
    slot = root / name
    slot.mkdir()
    fake_file(slot / "caption.sav", timestamp)
    fake_file(slot / "game_data.sav", timestamp)
    return slot


class ReliableSaveSyncTests(unittest.TestCase):
    def test_snapshot_factory_receives_the_stable_pair(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "botw_companion.save.load_hashes", return_value={HASH: (3, "LastSaveTime_Lower")}
        ):
            root = Path(tmp)
            slot = fake_slot(root, "0", 10)
            received = []

            def from_snapshot(snapshot: SaveSnapshot):
                received.append(snapshot)
                return {"source": str(snapshot.slot_path), "timestamp": snapshot.internal_timestamp}

            sync = ReliableSaveSync(
                root,
                lambda: self.fail("Le lecteur direct ne doit pas être utilisé"),
                stability_delay=0,
                snapshot_payload_factory=from_snapshot,
            )
            report = sync.report()
            expected_caption = (slot / "caption.sav").read_bytes()
            expected_game_data = (slot / "game_data.sav").read_bytes()
        self.assertEqual(report["source"], str(slot))
        self.assertEqual(report["timestamp"], 10)
        self.assertEqual(received[0].caption_data, expected_caption)
        self.assertEqual(received[0].game_data, expected_game_data)

    def test_windows_sharing_violation_keeps_the_last_report(self):
        locked = {"value": False}
        with tempfile.TemporaryDirectory() as tmp, patch(
            "botw_companion.save.load_hashes", return_value={HASH: (3, "LastSaveTime_Lower")}
        ):
            root = Path(tmp)
            slot = fake_slot(root, "0", 10)

            def windows_reader(path: Path) -> bytes:
                if locked["value"] and path.name == "game_data.sav":
                    raise PermissionError(32, "Le processus ne peut pas accéder au fichier")
                return path.read_bytes()

            sync = ReliableSaveSync(
                root,
                lambda: {"safe": True},
                stability_delay=0,
                read_bytes=windows_reader,
            )
            sync.report()
            locked["value"] = True
            future = time.time() + 1
            os.utime(slot / "game_data.sav", (future, future))
            result = sync.check(include_report=True)
        self.assertTrue(result["report"]["safe"])
        self.assertEqual(result["synchronisation"]["status"], "ecriture_en_cours")
        self.assertIn("accéder au fichier", result["synchronisation"]["error"])

    def test_two_reads_must_contain_identical_bytes_even_if_stats_do_not_change(self):
        unstable = {"value": False, "game_reads": 0}
        with tempfile.TemporaryDirectory() as tmp, patch(
            "botw_companion.save.load_hashes", return_value={HASH: (3, "LastSaveTime_Lower")}
        ):
            root = Path(tmp)
            slot = fake_slot(root, "0", 10)
            original = (slot / "game_data.sav").read_bytes()
            changed = original[:-5] + bytes([original[-5] ^ 1]) + original[-4:]

            def inconsistent_reader(path: Path) -> bytes:
                if unstable["value"] and path.name == "game_data.sav":
                    unstable["game_reads"] += 1
                    return original if unstable["game_reads"] == 1 else changed
                return path.read_bytes()

            sync = ReliableSaveSync(
                root,
                lambda: {"safe": True},
                stability_delay=0,
                read_bytes=inconsistent_reader,
            )
            sync.report()
            unstable["value"] = True
            future = time.time() + 1
            os.utime(slot / "game_data.sav", (future, future))
            result = sync.check(include_report=True)
        self.assertTrue(result["report"]["safe"])
        self.assertEqual(result["synchronisation"]["status"], "ecriture_en_cours")

    def test_temporarily_missing_windows_source_keeps_the_last_report(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "botw_companion.save.load_hashes", return_value={HASH: (3, "LastSaveTime_Lower")}
        ):
            root = Path(tmp) / "Ryujinx" / "bis" / "user" / "save" / "botw"
            root.mkdir(parents=True)
            fake_slot(root, "0", 10)
            sync = ReliableSaveSync(root, lambda: {"safe": True}, stability_delay=0)
            sync.report()
            unavailable = root.with_name("botw-offline")
            root.rename(unavailable)
            result = sync.check(include_report=True)
        self.assertTrue(result["report"]["safe"])
        self.assertEqual(result["synchronisation"]["status"], "source_indisponible")

    def test_auto_detection_compares_standard_and_portable_sources(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "botw_companion.save.load_hashes", return_value={HASH: (3, "LastSaveTime_Lower")}
        ):
            base = Path(tmp)
            standard = base / "AppData" / "Roaming" / "Ryujinx" / "bis" / "user" / "save" / "botw"
            portable = base / "Ryujinx" / "portable" / "bis" / "user" / "save" / "botw"
            standard.mkdir(parents=True)
            portable.mkdir(parents=True)
            fake_slot(standard, "0", 10)
            newest = fake_slot(portable, "1", 20)
            with patch(
                "botw_companion.synchronization.find_ryujinx_game_save_roots",
                return_value=[standard, portable],
            ):
                sync = ReliableSaveSync(
                    None,
                    lambda: {"fallback": True},
                    stability_delay=0,
                    snapshot_payload_factory=lambda snapshot: {"slot_path": str(snapshot.slot_path)},
                )
                report = sync.report()
        self.assertEqual(report["slot_path"], str(newest))
        self.assertEqual(report["synchronisation"]["source_root"], str(portable))
        self.assertEqual(report["synchronisation"]["source_kind"], "portable")

    def test_locked_current_portable_source_never_falls_back_to_older_standard_save(self):
        locked = {"value": False}
        with tempfile.TemporaryDirectory() as tmp, patch(
            "botw_companion.save.load_hashes", return_value={HASH: (3, "LastSaveTime_Lower")}
        ):
            base = Path(tmp)
            standard = base / "standard" / "botw"
            portable = base / "portable" / "botw"
            standard.mkdir(parents=True)
            portable.mkdir(parents=True)
            fake_slot(standard, "0", 10)
            current = fake_slot(portable, "1", 20)

            def windows_parse(path: Path):
                if locked["value"] and path == current / "caption.sav":
                    raise PermissionError(32, "Sharing violation")
                return real_parse_file(path)

            with patch(
                "botw_companion.synchronization.find_ryujinx_game_save_roots",
                return_value=[standard, portable],
            ), patch("botw_companion.synchronization.parse_file", side_effect=windows_parse):
                sync = ReliableSaveSync(None, lambda: {"selected": "portable"}, stability_delay=0)
                sync.report()
                locked["value"] = True
                result = sync.check(include_report=True)
        self.assertEqual(result["report"]["selected"], "portable")
        self.assertEqual(result["synchronisation"]["slot"], "1")
        self.assertNotEqual(result["synchronisation"]["status"], "actualise")

    def test_unchanged_save_reuses_the_last_report(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "botw_companion.save.load_hashes", return_value={HASH: (3, "LastSaveTime_Lower")}
        ):
            root = Path(tmp)
            fake_slot(root, "0", 10)
            calls = []
            sync = ReliableSaveSync(root, lambda: calls.append(1) or {"result": len(calls)},
                                    stability_delay=0)
            first = sync.report()
            second = sync.check()
        self.assertEqual(first["result"], 1)
        self.assertEqual(len(calls), 1)
        self.assertFalse(second["changed"])
        self.assertEqual(second["synchronisation"]["status"], "a_jour")

    def test_changed_content_creates_a_new_revision(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "botw_companion.save.load_hashes", return_value={HASH: (3, "LastSaveTime_Lower")}
        ):
            root = Path(tmp)
            slot = fake_slot(root, "0", 10)
            calls = []
            sync = ReliableSaveSync(root, lambda: calls.append(1) or {"result": len(calls)},
                                    stability_delay=0)
            sync.report()
            fake_file(slot / "game_data.sav", 11)
            os.utime(slot / "game_data.sav", None)
            result = sync.check()
        self.assertTrue(result["changed"])
        self.assertEqual(result["report"]["result"], 2)
        self.assertEqual(result["synchronisation"]["report_revision"], 2)

    def test_partial_write_never_replaces_the_cached_report(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "botw_companion.save.load_hashes", return_value={HASH: (3, "LastSaveTime_Lower")}
        ):
            root = Path(tmp)
            slot = fake_slot(root, "0", 10)
            calls = []
            sync = ReliableSaveSync(root, lambda: calls.append(1) or {"safe": len(calls)},
                                    stability_delay=0)
            sync.report()
            (slot / "game_data.sav").write_bytes(b"partial write")
            result = sync.check(include_report=True)
        self.assertEqual(result["report"]["safe"], 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["synchronisation"]["status"], "ecriture_en_cours")

    def test_analysis_error_keeps_the_last_good_report(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "botw_companion.save.load_hashes", return_value={HASH: (3, "LastSaveTime_Lower")}
        ):
            root = Path(tmp)
            slot = fake_slot(root, "0", 10)
            fail = {"value": False}
            def factory():
                if fail["value"]:
                    raise RuntimeError("erreur simulée")
                return {"safe": True}
            sync = ReliableSaveSync(root, factory, stability_delay=0)
            sync.report()
            fail["value"] = True
            fake_file(slot / "game_data.sav", 12)
            result = sync.check(include_report=True)
        self.assertTrue(result["report"]["safe"])
        self.assertEqual(result["synchronisation"]["status"], "erreur_analyse")
        self.assertIn("erreur simulée", result["synchronisation"]["error"])

    def test_newer_slot_is_detected_and_reported(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "botw_companion.save.load_hashes", return_value={HASH: (3, "LastSaveTime_Lower")}
        ):
            root = Path(tmp)
            fake_slot(root, "0", 10)
            sync = ReliableSaveSync(root, lambda: {"ok": True}, stability_delay=0)
            sync.report()
            fake_slot(root, "1", 20)
            result = sync.check()
        self.assertEqual(result["synchronisation"]["slot"], "1")
        self.assertTrue(any("Passage du slot 0 au slot 1" in event["message"]
                            for event in result["synchronisation"]["events"]))

    def test_incomplete_new_slot_is_reported_without_switching_backwards(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "botw_companion.save.load_hashes", return_value={HASH: (3, "LastSaveTime_Lower")}
        ):
            root = Path(tmp)
            fake_slot(root, "0", 10)
            sync = ReliableSaveSync(root, lambda: {"safe": True}, stability_delay=0)
            sync.report()
            partial = root / "1"
            partial.mkdir()
            (partial / "caption.sav").write_bytes(b"partial")
            (partial / "game_data.sav").write_bytes(b"partial")
            future = time.time() + 2
            os.utime(partial / "caption.sav", (future, future))
            os.utime(partial / "game_data.sav", (future, future))
            waiting = sync.check(include_report=True)
            fake_file(partial / "caption.sav", 20)
            fake_file(partial / "game_data.sav", 20)
            os.utime(partial / "caption.sav", (future + 1, future + 1))
            os.utime(partial / "game_data.sav", (future + 1, future + 1))
            completed = sync.check()
        self.assertEqual(waiting["report"]["safe"], True)
        self.assertIn("Nouveau slot 1", waiting["synchronisation"]["status_label"])
        self.assertEqual(completed["synchronisation"]["slot"], "1")

    def test_concurrent_checks_run_only_one_analysis(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "botw_companion.save.load_hashes", return_value={HASH: (3, "LastSaveTime_Lower")}
        ):
            root = Path(tmp)
            fake_slot(root, "0", 10)
            calls = 0
            guard = threading.Lock()

            def factory():
                nonlocal calls
                with guard:
                    calls += 1
                time.sleep(0.03)
                return {"ok": True}
            sync = ReliableSaveSync(root, factory, stability_delay=0)
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _index: sync.report(), range(4)))
        self.assertEqual(calls, 1)
        self.assertTrue(all(result["ok"] for result in results))

    def test_recently_touched_old_slot_never_blocks_the_current_slot(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "botw_companion.save.load_hashes", return_value={HASH: (3, "LastSaveTime_Lower")}
        ):
            root = Path(tmp)
            old = fake_slot(root, "0", 10)
            fake_slot(root, "1", 20)
            calls = []
            sync = ReliableSaveSync(root, lambda: calls.append(1) or {"safe": len(calls)},
                                    stability_delay=0)
            sync.report()
            future = time.time() + 30
            os.utime(old / "caption.sav", (future, future))
            os.utime(old / "game_data.sav", (future, future))
            result = sync.check(include_report=True)
        self.assertEqual(result["report"]["safe"], 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["synchronisation"]["slot"], "1")
        self.assertEqual(result["synchronisation"]["status"], "ancien_slot_modifie")
        self.assertEqual(result["synchronisation"]["ignored_slot"], "0")

    def test_incomplete_candidate_times_out_then_recovers_automatically(self):
        clock = [100.0]
        with tempfile.TemporaryDirectory() as tmp, patch(
            "botw_companion.save.load_hashes", return_value={HASH: (3, "LastSaveTime_Lower")}
        ):
            root = Path(tmp)
            fake_slot(root, "0", 10)
            sync = ReliableSaveSync(root, lambda: {"safe": True}, stability_delay=0,
                                    max_wait_seconds=5, monotonic_clock=lambda: clock[0])
            sync.report()
            partial = root / "1"
            partial.mkdir()
            (partial / "caption.sav").write_bytes(b"partial")
            (partial / "game_data.sav").write_bytes(b"partial")
            future = time.time() + 30
            os.utime(partial / "caption.sav", (future, future))
            os.utime(partial / "game_data.sav", (future, future))
            waiting = sync.check(include_report=True)
            clock[0] += 6
            timed_out = sync.check(include_report=True)
            fake_file(partial / "caption.sav", 20)
            fake_file(partial / "game_data.sav", 20)
            recovered = sync.check()
        self.assertEqual(waiting["synchronisation"]["status"], "ecriture_en_cours")
        self.assertEqual(timed_out["synchronisation"]["status"], "fichier_corrompu")
        self.assertTrue(timed_out["report"]["safe"])
        self.assertEqual(recovered["synchronisation"]["status"], "nouveau_slot_valide")
        self.assertEqual(recovered["synchronisation"]["slot"], "1")

    def test_corrupted_current_slot_never_regresses_to_an_older_save(self):
        clock = [10.0]
        with tempfile.TemporaryDirectory() as tmp, patch(
            "botw_companion.save.load_hashes", return_value={HASH: (3, "LastSaveTime_Lower")}
        ):
            root = Path(tmp)
            fake_slot(root, "0", 10)
            current = fake_slot(root, "1", 20)
            sync = ReliableSaveSync(root, lambda: {"selected": "latest"}, stability_delay=0,
                                    max_wait_seconds=2, monotonic_clock=lambda: clock[0])
            sync.report()
            (current / "caption.sav").write_bytes(b"broken")
            waiting = sync.check(include_report=True)
            clock[0] += 3
            failed = sync.check(include_report=True)
        self.assertEqual(waiting["synchronisation"]["status"], "ecriture_en_cours")
        self.assertEqual(failed["synchronisation"]["status"], "fichier_corrompu")
        self.assertEqual(failed["synchronisation"]["slot"], "1")
        self.assertEqual(failed["report"]["selected"], "latest")

    def test_switches_between_normal_and_expert_by_internal_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "botw_companion.save.load_hashes", return_value={HASH: (3, "LastSaveTime_Lower")}
        ):
            root = Path(tmp)
            fake_slot(root, "0", 10)
            sync = ReliableSaveSync(root, lambda: {"ok": True}, stability_delay=0)
            normal = sync.report()["synchronisation"]
            fake_slot(root, "6", 20)
            expert = sync.check()["synchronisation"]
            fake_slot(root, "1", 30)
            normal_again = sync.check()["synchronisation"]
        self.assertEqual(normal["save_mode"], "normal")
        self.assertEqual(expert["save_mode"], "expert")
        self.assertEqual(expert["status"], "nouveau_slot_valide")
        self.assertEqual(normal_again["save_mode"], "normal")
        self.assertEqual(normal_again["slot"], "1")