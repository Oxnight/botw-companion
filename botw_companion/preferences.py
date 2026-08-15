from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import threading

from .manual_tracking import ManualTrackingError
from .persistence import atomic_write_json, copy_valid_backup, read_json
from .platforms import companion_data_dir


SCHEMA_VERSION = 1
ALLOWED_VALUES = {
    "sync_interval": {5, 10, 15, 30, 60},
    "map_content_mode": {"automatique", "base", "dlc"},
    "completion_profile": {"automatique", "base", "dlc", "amiibo", "expert", "automatic_only"},
    "game_mode_filter": {"save", "all", "normal", "expert"},
    "dsu_mode": {"integrated", "external", "disabled"},
}


def default_preferences_path() -> Path:
    return companion_data_dir() / "preferences.json"


class PreferenceStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_preferences_path()
        self.backup_path = self.path.with_suffix(".backup.json")
        self._lock = threading.RLock()

    @staticmethod
    def _empty() -> dict:
        return {"schema_version": SCHEMA_VERSION, "revision": 0, "updated_at": None, "values": {}}

    @classmethod
    def _validate(cls, payload: object) -> dict:
        if not isinstance(payload, dict) or not isinstance(payload.get("values", {}), dict):
            raise ManualTrackingError("Format des préférences invalide")
        version = payload.get("schema_version", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise ManualTrackingError("Version des préférences non prise en charge")
        revision = payload.get("revision", 0)
        if not isinstance(revision, int) or revision < 0:
            raise ManualTrackingError("Révision des préférences invalide")
        values = {}
        for key, value in payload.get("values", {}).items():
            if key not in ALLOWED_VALUES or value not in ALLOWED_VALUES[key]:
                raise ManualTrackingError(f"Préférence invalide : {key}")
            values[key] = value
        return {
            "schema_version": SCHEMA_VERSION,
            "revision": revision,
            "updated_at": payload.get("updated_at"),
            "values": values,
        }

    def _read_file(self, path: Path) -> dict:
        return self._validate(read_json(path))

    def load(self) -> dict:
        with self._lock:
            if not self.path.exists():
                return self._empty()
            try:
                return self._read_file(self.path)
            except ManualTrackingError as exc:
                if "Version" in str(exc):
                    raise
                return self._load_backup_or_raise()
            except (OSError, json.JSONDecodeError):
                return self._load_backup_or_raise()

    def _load_backup_or_raise(self) -> dict:
        if self.backup_path.exists():
            try:
                return self._read_file(self.backup_path)
            except (OSError, json.JSONDecodeError, ManualTrackingError):
                pass
        raise ManualTrackingError(
            f"Les préférences sont illisibles. Une copie est conservée dans {self.path.parent}"
        )

    def _write(self, payload: dict) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                self._read_file(self.path)
            except (OSError, json.JSONDecodeError, ManualTrackingError):
                pass
            else:
                copy_valid_backup(self.path, self.backup_path)
        return atomic_write_json(self.path, payload)

    def replace(self, incoming: object, expected_revision: int | None = None) -> dict:
        clean = self._validate(incoming)
        with self._lock:
            current = self.load()
            if expected_revision is not None and expected_revision != current["revision"]:
                raise ManualTrackingError("Les préférences ont changé dans une autre fenêtre; actualise puis réessaie")
            clean["revision"] = current["revision"] + 1
            clean["updated_at"] = datetime.now(timezone.utc).isoformat()
            return self._write(clean)

    def update(self, values: object, expected_revision: int | None = None) -> dict:
        if not isinstance(values, dict):
            raise ManualTrackingError("Préférences invalides")
        with self._lock:
            current = self.load()
            if expected_revision is not None and expected_revision != current["revision"]:
                raise ManualTrackingError("Les préférences ont changé dans une autre fenêtre; actualise puis réessaie")
            candidate = {**current, "values": {**current["values"], **values}}
            return self.replace(candidate, current["revision"])