import json
from importlib.resources import files
import unittest

from botw_companion.analyzer import analyze
from botw_companion.localization import localize_catalog
from botw_companion.resources import (load_catalog,
                                      load_cartography_reference,
                                      load_runtime_nomenclature_audit)


class RuntimeCacheTests(unittest.TestCase):
    def test_compiled_french_catalog_is_exactly_equivalent_to_sources(self):
        raw = json.loads(
            files("botw_companion.data").joinpath("catalog.json").read_text()
        )
        self.assertEqual(load_catalog(), localize_catalog(raw))

    def test_compiled_nomenclature_audit_is_exactly_equivalent(self):
        dynamic = analyze(
            {}, use_precompiled_nomenclature_audit=False
        )["audit_nomenclature"]
        self.assertEqual(load_runtime_nomenclature_audit(), dynamic)

    def test_compiled_french_cartography_is_exactly_equivalent_to_sources(self):
        raw = json.loads(
            files("botw_companion.data").joinpath("cartography_reference.json").read_text()
        )
        self.assertEqual(load_cartography_reference(), localize_catalog(raw))


if __name__ == "__main__":
    unittest.main()