import unittest

from botw_companion.blood_moon import blood_moon_status


class BloodMoonTests(unittest.TestCase):
    def test_latest_reference_save_exposes_all_three_timeline_steps(self):
        result = blood_moon_status({
            "FirstTouchdown": True,
            "WM_BloodyMoonTimer": 944.6406860351562,
            "WM_Time": 157.98471069335938,
            "WM_BloodyDay": False,
            "WM_bloodyEndReserveTimer": 0,
        })
        self.assertEqual(result["game_time_label"], "10:31")
        self.assertEqual(result["active_seconds_until_threshold"], 6302)
        self.assertEqual(result["active_seconds_until_scheduled"], 6569)
        self.assertEqual(result["active_seconds_until_event"], 8009)

    def test_real_reference_save_uses_internal_timer(self):
        result = blood_moon_status({
            "FirstTouchdown": True,
            "WM_BloodyMoonTimer": 2061.185791015625,
            "WM_Time": 286.1658020019531,
            "WM_BloodyDay": False,
            "WM_bloodyEndReserveTimer": 0,
        })
        self.assertTrue(result["available"])
        self.assertEqual(result["status"], "counting")
        self.assertEqual(result["game_time_label"], "19:04")
        self.assertEqual(result["active_seconds_until_threshold"], 1836)
        self.assertEqual(result["active_seconds_until_event"], 4616)
        self.assertAlmostEqual(result["timer_progress_percent"], 81.79, places=2)

    def test_scheduled_moon_targets_next_midnight(self):
        result = blood_moon_status({
            "FirstTouchdown": True,
            "WM_BloodyMoonTimer": 12.0,
            "WM_Time": 300.0,
            "WM_BloodyDay": True,
        })
        self.assertTrue(result["scheduled"])
        self.assertEqual(result["active_seconds_until_event"], 240)
        self.assertEqual(result["active_seconds_until_threshold"], 0)

    def test_midnight_scheduled_moon_means_the_following_midnight(self):
        result = blood_moon_status({
            "FirstTouchdown": True,
            "WM_BloodyMoonTimer": 0.0,
            "WM_Time": 0.0,
            "WM_BloodyDay": True,
        })
        self.assertEqual(result["active_seconds_until_event"], 24 * 60)

    def test_counter_is_unavailable_before_leaving_plateau(self):
        result = blood_moon_status({"WM_BloodyMoonTimer": 100.0, "WM_Time": 20.0})
        self.assertFalse(result["available"])
        self.assertEqual(result["status"], "not_started")

    def test_missing_internal_fields_are_not_invented(self):
        result = blood_moon_status({"FirstTouchdown": True})
        self.assertFalse(result["available"])
        self.assertEqual(result["status"], "missing_data")

    def test_recent_blood_moon_is_not_mistaken_for_scheduled_flag(self):
        result = blood_moon_status({
            "FirstTouchdown": True,
            "WM_BloodyMoonTimer": 360.0,
            "WM_Time": 0.0,
            "WM_BloodyDay": True,
            "WM_bloodyEndReserveTimer": 50,
        })
        self.assertFalse(result["scheduled"])
        self.assertEqual(result["status"], "just_occurred")


if __name__ == "__main__":
    unittest.main()