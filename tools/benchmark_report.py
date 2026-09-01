#!/usr/bin/env python3
"""Measure the legacy report and the progressive browser transport."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from botw_companion.cli import _payload
from botw_companion.report_views import bootstrap_report, compact_catalog


def encoded(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def functional_fingerprint(items: list[dict]) -> str:
    contract = sorted((item.get("tracking_id"), item.get("termine"), item.get("commence"),
                       item.get("x"), item.get("z"), item.get("filter_type"))
                      for item in items)
    return sha256(encoded(contract)).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("save", help="Dossier de sauvegarde ou racine des slots")
    args = parser.parse_args()
    tracemalloc.start()
    started = time.perf_counter()
    report = _payload(args.save)
    analysis_seconds = time.perf_counter() - started
    started = time.perf_counter()
    bootstrap = bootstrap_report(report)
    bootstrap_seconds = time.perf_counter() - started
    started = time.perf_counter()
    catalog = compact_catalog(report)
    catalog_seconds = time.perf_counter() - started
    started = time.perf_counter()
    legacy_encoded = encoded(report)
    legacy_serialization_seconds = time.perf_counter() - started
    started = time.perf_counter()
    bootstrap_encoded = encoded(bootstrap)
    catalog_encoded = encoded(catalog)
    browser_serialization_seconds = time.perf_counter() - started
    legacy_bytes = len(legacy_encoded)
    browser_bytes = len(bootstrap_encoded) + len(catalog_encoded)
    _, peak = tracemalloc.get_traced_memory()
    original_items = [*report["elements"], *report["map_layers"]]
    compact_items = [*catalog["elements"], *catalog["map_layers"]]
    result = {
        "analysis_seconds": round(analysis_seconds, 3),
        "bootstrap_seconds": round(bootstrap_seconds, 3),
        "catalog_seconds": round(catalog_seconds, 3),
        "legacy_serialization_seconds": round(legacy_serialization_seconds, 3),
        "browser_serialization_seconds": round(browser_serialization_seconds, 3),
        "legacy_report_bytes": legacy_bytes,
        "bootstrap_bytes": len(bootstrap_encoded),
        "catalog_bytes": len(catalog_encoded),
        "browser_total_bytes": browser_bytes,
        "browser_reduction_percent": round(100 * (1 - browser_bytes / legacy_bytes), 2),
        "python_peak_bytes": peak,
        "items": len(original_items),
        "functional_fingerprint": functional_fingerprint(original_items),
        "compact_fingerprint": functional_fingerprint(compact_items),
        "functionally_identical": functional_fingerprint(original_items) == functional_fingerprint(compact_items),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()