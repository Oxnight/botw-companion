import unittest

from tools.release_lookup import ReleaseLookupError, find_release_id


class ReleaseLookupTests(unittest.TestCase):
    def test_paginated_metadata_resolves_a_draft_by_exact_tag(self):
        payload = [
            [{"id": 11, "tag_name": "v0.9.0", "draft": False}],
            [{"id": 42, "tag_name": "v1.0.0-rc.2", "draft": True}],
        ]
        self.assertEqual(find_release_id(payload, "v1.0.0-rc.2", "draft"), 42)

    def test_state_filter_never_confuses_a_draft_with_a_public_release(self):
        payload = [[{"id": 42, "tag_name": "v1.0.0-rc.2", "draft": True}]]
        with self.assertRaisesRegex(ReleaseLookupError, "not found"):
            find_release_id(payload, "v1.0.0-rc.2", "published")

    def test_missing_ambiguous_and_malformed_results_are_rejected(self):
        with self.assertRaisesRegex(ReleaseLookupError, "not found"):
            find_release_id([], "v1.0.0")
        with self.assertRaisesRegex(ReleaseLookupError, "ambiguous"):
            find_release_id([
                {"id": 1, "tag_name": "v1.0.0", "draft": False},
                {"id": 2, "tag_name": "v1.0.0", "draft": False},
            ], "v1.0.0")
        with self.assertRaisesRegex(ReleaseLookupError, "database id"):
            find_release_id([{"id": "42", "tag_name": "v1.0.0", "draft": False}],
                            "v1.0.0")


if __name__ == "__main__":
    unittest.main()
