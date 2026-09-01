import unittest
from pathlib import Path

from botw_companion.cli import _save_context


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