import tempfile
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

from botw_companion.save import (
    SaveError,
    discover_ryujinx_save_root,
    find_game_save_roots,
    find_latest_slot,
    find_ryujinx_game_save_roots,
    parse_data,
    parse_file,
    parse_inventory,
)


def fake_save(path: Path, timestamp: int) -> None:
    marker = b"\x00\x00\x00\x01\xff\xff\xff\xff\x00\x00\x00\x01"
    entry = struct.pack(">Ii", 195546944, timestamp)
    path.write_bytes(marker + entry + b"\xff\xff\xff\xff")


class SaveTests(unittest.TestCase):
    def test_in_memory_parser_matches_the_file_parser(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "botw_companion.save.load_hashes", return_value={195546944: (3, "LastSaveTime_Lower")}
        ):
            path = Path(tmp) / "caption.sav"
            fake_save(path, 42)
            self.assertEqual(parse_data(path.read_bytes(), path), parse_file(path))

    def test_parses_inventory_names_and_quantities(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "game_data.sav"
            data = bytearray(0x500)
            data[:12] = b"\x00\x00\x00\x01\xff\xff\xff\xff\x01\x00\x00\x00"
            names_base = 0x88
            quantities_base = 0x388
            struct.pack_into("<I", data, names_base - 4, 0x5F283289)
            struct.pack_into("<I", data, quantities_base - 4, 0x6A09FC59)
            for slot, (actor, quantity) in enumerate((("Armor_150_Upper", 0), ("Item_Enemy_18", 23))):
                raw = actor.encode().ljust(64, b"\0")
                for part in range(16):
                    start = names_base + slot * 0x80 + part * 8
                    data[start:start + 4] = raw[part * 4:part * 4 + 4]
                struct.pack_into("<I", data, quantities_base + slot * 8, quantity)
            data[-4:] = b"\xff\xff\xff\xff"
            path.write_bytes(data)
            inventory = parse_inventory(path)
        self.assertEqual(inventory[0], {"slot": 0, "id": "Armor_150_Upper", "quantite": 0, "armure": True})
        self.assertEqual(inventory[1]["quantite"], 23)

    def test_latest_slot_uses_internal_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, timestamp in (("0", 10), ("1", 20)):
                slot = root / name
                slot.mkdir()
                fake_save(slot / "caption.sav", timestamp)
                fake_save(slot / "game_data.sav", timestamp)
            with patch("botw_companion.save.load_hashes", return_value={195546944: (3, "LastSaveTime_Lower")}):
                self.assertEqual(find_latest_slot(root).path.name, "1")

    def test_rejects_invalid_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.sav"
            path.write_bytes(b"bad")
            with self.assertRaises(SaveError):
                parse_file(path)

    def test_discovers_botw_inside_ryujinx_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "bis/user/save/0000000000000001/0"
            slot = root / "1"
            slot.mkdir(parents=True)
            fake_save(slot / "caption.sav", 42)
            fake_save(slot / "game_data.sav", 42)
            with patch("botw_companion.save.load_hashes", return_value={195546944: (3, "LastSaveTime_Lower")}):
                found = discover_ryujinx_save_root([Path(tmp) / "bis/user/save"])
            self.assertEqual(found, root)

    def test_candidate_discovery_includes_a_partially_written_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            save_root = Path(tmp) / "bis/user/save"
            botw_root = save_root / "0000000000000001" / "0"
            slot = botw_root / "1"
            slot.mkdir(parents=True)
            (slot / "caption.sav").write_bytes(b"partial")
            self.assertEqual(find_ryujinx_game_save_roots([save_root]), [botw_root])

    def test_discovers_botw_inside_cemu_mlc_tree(self):
        from botw_companion.emulators import CEMU
        with tempfile.TemporaryDirectory() as tmp:
            save_root = Path(tmp) / "mlc01/usr/save"
            account = save_root / "00050000/101C9500/user/80000001"
            slot = account / "1"
            slot.mkdir(parents=True)
            fake_save(slot / "caption.sav", 50)
            fake_save(slot / "game_data.sav", 50)
            found = find_game_save_roots([(CEMU, save_root)])
            self.assertEqual(found, [(CEMU, account)])


if __name__ == "__main__":
    unittest.main()