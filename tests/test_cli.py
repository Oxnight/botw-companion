import unittest
from pathlib import Path
from unittest.mock import patch

from botw_companion.cli import _build_payload, _save_context
from botw_companion.save import SaveSlot


class CliProfileTests(unittest.TestCase):
    def test_slots_six_and_seven_are_expert_slots(self):
        for slot in (6, 7):
            with self.subTest(slot=slot):
                context = _save_context(Path(f"/saves/{slot}"), {})
                self.assertEqual(context["mode"], "expert")
                self.assertIn(f"slot {slot}", context["detection"])

    def test_numbered_normal_slot_has_priority_over_last_play_flag(self):
        context = _save_context(Path("/saves/1"), {"IsLastPlayHardMode": True})
        self.assertEqual(context["mode"], "normal")
        self.assertEqual(context["detection"], "slot 1 réservé au mode normal")

    def test_master_mode_flag_is_fallback_for_an_isolated_folder(self):
        context = _save_context(Path("/saves/export"), {"IsLastPlayHardMode": True})
        self.assertEqual(context["mode"], "expert")
        self.assertIn("numéro de slot indisponible", context["detection"])

    def test_normal_slot_without_flag_stays_normal(self):
        context = _save_context(Path("/saves/1"), {})
        self.assertEqual(context["mode"], "normal")

    def test_caption_game_clear_is_merged_into_analysis(self):
        with (
            patch("botw_companion.cli.analyze", return_value={}) as analyze,
            patch("botw_companion.cli.blood_moon_status", return_value={}),
        ):
            _build_payload(
                SaveSlot(Path("/saves/1"), 0),
                {"GameClear": True},
                {"GameClear": False, "GanonQuest_Finished": False},
                [],
                "Ryujinx Windows",
            )
        self.assertIs(analyze.call_args.args[0]["GameClear"], True)
        self.assertIs(analyze.call_args.args[0]["GanonQuest_Finished"], False)
