import json
import unittest

from botw_companion.analyzer import analyze
from botw_companion.report_views import ReportViewCache, bootstrap_report, compact_catalog


class ReportViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = analyze({})

    def test_bootstrap_preserves_every_counter_but_not_duplicate_lists(self):
        bootstrap = bootstrap_report(self.report)
        self.assertNotIn("elements", bootstrap)
        self.assertNotIn("map_layers", bootstrap)
        for category, original in self.report["categories"].items():
            compact = bootstrap["categories"][category]
            self.assertEqual((compact["faits"], compact["total"]),
                             (original["faits"], original["total"]))
            self.assertFalse({"elements", "restants", "termines"} & compact.keys())

    def test_catalog_preserves_ids_statuses_coordinates_and_filters(self):
        catalog = compact_catalog(self.report)
        original = [*self.report["elements"], *self.report["map_layers"]]
        compact = [*catalog["elements"], *catalog["map_layers"]]
        self.assertEqual(len(compact), len(original))
        expected = {(item["tracking_id"], item.get("termine"), item.get("x"), item.get("z"),
                     item.get("filter_type")) for item in original}
        actual = {(item["tracking_id"], item.get("termine"), item.get("x"), item.get("z"),
                   item.get("filter_type")) for item in compact}
        self.assertEqual(actual, expected)
        self.assertTrue(all("guide" not in item for item in compact))

    def test_browser_payload_is_less_than_a_quarter_of_the_legacy_report(self):
        legacy = len(json.dumps(self.report, ensure_ascii=False).encode())
        bootstrap = len(json.dumps(bootstrap_report(self.report), ensure_ascii=False).encode())
        catalog = len(json.dumps(compact_catalog(self.report), ensure_ascii=False).encode())
        self.assertLess(bootstrap + catalog, legacy * 0.25)

    def test_details_are_loaded_by_stable_tracking_id(self):
        cache = ReportViewCache()
        target = self.report["elements"][0]
        detail = cache.detail(self.report, target["tracking_id"])
        self.assertEqual(detail, target)
        self.assertIn("guide", detail)

    def test_heavy_views_are_built_only_when_requested(self):
        cache = ReportViewCache()
        cache.bootstrap(self.report)
        self.assertIsNone(cache._catalog)
        self.assertEqual(cache._details, {})
        cache.catalog(self.report)
        self.assertIsNotNone(cache._catalog)
        self.assertEqual(cache._details, {})