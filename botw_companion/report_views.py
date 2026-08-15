from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import threading


CATALOG_HEAVY_FIELDS = {
    "guide", "interior_chests", "interior_position", "solution_evidence",
    "quest_evidence", "trial_rooms", "recettes",
}
CATEGORY_LIST_FIELDS = {"elements", "restants", "termines"}


def report_revision_key(report: dict) -> str:
    sync = report.get("synchronisation") or {}
    if sync.get("fingerprint"):
        return str(sync["fingerprint"])
    save = report.get("sauvegarde") or {}
    return sha256(json.dumps({"slot": save.get("slot"), "date": save.get("date"),
                              "counts": (len(report.get("elements", [])),
                                         len(report.get("map_layers", [])))},
                             sort_keys=True).encode()).hexdigest()[:16]


def compact_item(item: dict) -> dict:
    # Ces vues sont uniquement sérialisées. Réutiliser les valeurs immuables du
    # rapport évite une seconde copie complète de milliers de marqueurs.
    return {key: value for key, value in item.items()
            if key not in CATALOG_HEAVY_FIELDS}


def bootstrap_report(report: dict) -> dict:
    result = {}
    for key, value in report.items():
        if key in {"elements", "map_layers"}:
            continue
        if key == "categories":
            result[key] = {
                category: {field: deepcopy(field_value) for field, field_value in data.items()
                           if field not in CATEGORY_LIST_FIELDS}
                for category, data in value.items()
            }
        else:
            result[key] = deepcopy(value)
    result.update({
        "report_transport_schema": 1,
        "report_revision_key": report_revision_key(report),
        "catalog": {
            "elements": len(report.get("elements", [])),
            "map_layers": len(report.get("map_layers", [])),
            "loaded": False,
            "endpoint": "/api/catalog",
        },
    })
    return result


def compact_catalog(report: dict) -> dict:
    return {
        "schema_version": 1,
        "report_revision_key": report_revision_key(report),
        "elements": [compact_item(item) for item in report.get("elements", [])],
        "map_layers": [compact_item(item) for item in report.get("map_layers", [])],
    }


class ReportViewCache:
    """Builds immutable browser views once per analyzed report."""

    def __init__(self):
        self._lock = threading.RLock()
        self._report_object: int | None = None
        self._bootstrap: dict | None = None
        self._catalog: dict | None = None
        self._details: dict[str, dict] = {}

    def _select_report(self, report: dict) -> None:
        identity = id(report)
        if identity == self._report_object:
            return
        self._report_object = identity
        self._bootstrap = None
        self._catalog = None
        self._details = {}

    def bootstrap(self, report: dict) -> dict:
        with self._lock:
            self._select_report(report)
            if self._bootstrap is None:
                self._bootstrap = bootstrap_report(report)
            return self._bootstrap  # treated as immutable by the JSON encoder

    def catalog(self, report: dict) -> dict:
        with self._lock:
            self._select_report(report)
            if self._catalog is None:
                self._catalog = compact_catalog(report)
            return self._catalog

    def detail(self, report: dict, tracking_id: str) -> dict | None:
        with self._lock:
            self._select_report(report)
            if not self._details:
                self._details = {
                    item["tracking_id"]: item
                    for item in [*report.get("elements", []), *report.get("map_layers", [])]
                    if item.get("tracking_id")
                }
            return self._details.get(tracking_id)