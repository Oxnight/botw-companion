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
    return {key: deepcopy(value) for key, value in item.items()
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

    def _prepare(self, report: dict) -> None:
        identity = id(report)
        if identity == self._report_object:
            return
        self._report_object = identity
        self._bootstrap = bootstrap_report(report)
        self._catalog = compact_catalog(report)
        self._details = {
            item["tracking_id"]: item
            for item in [*report.get("elements", []), *report.get("map_layers", [])]
            if item.get("tracking_id")
        }

    def bootstrap(self, report: dict) -> dict:
        with self._lock:
            self._prepare(report)
            return self._bootstrap  # treated as immutable by the JSON encoder

    def catalog(self, report: dict) -> dict:
        with self._lock:
            self._prepare(report)
            return self._catalog

    def detail(self, report: dict, tracking_id: str) -> dict | None:
        with self._lock:
            self._prepare(report)
            return self._details.get(tracking_id)