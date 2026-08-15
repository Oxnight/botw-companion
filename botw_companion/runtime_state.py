from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import threading

from .manual_tracking import ManualTrackingError
from .persistence import atomic_write_json, copy_valid_backup, read_json
from .platforms import companion_data_dir


SCHEMA_VERSION = 1
MAX_EVENTS = 12


def default_runtime_state_path() -> Path:
    return companion_data_dir() / "runtime_state.json"


class RuntimeStateStore:
    """État local non exportable : dernière source et historique de synchronisation."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_runtime_state_path()
        self.backup_path = self.path.with_suffix(".backup.json")
        self._lock = threading.RLock()

    @staticmethod
    def _empty() -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "updated_at": None,
            "last_save_source": None,
            "last_slot": None,
            "last_save_mode": None,
            "last_save_timestamp": None,
            "source_kind": None,
            "synchronization_events": [],
        }

    @classmethod
    def _validate(cls, payload: object) -> dict:
        if not isinstance(payload, dict) or payload.get("schema_version", SCHEMA_VERSION) != SCHEMA_VERSION:
            raise ManualTrackingError("Format de l’état local invalide")
        events = payload.get("synchronization_events", [])
        if not isinstance(events, list):
            raise ManualTrackingError("Historique de synchronisation invalide")
        clean_events = []
        for event in events[:MAX_EVENTS]:
            if not isinstance(event, dict):
                raise ManualTrackingError("Événement de synchronisation invalide")
            clean_events.append({
                key: value
                for key in ("at", "kind", "message")
                if isinstance((value := event.get(key)), str) and len(value) <= 1000
            })
        result = cls._empty()
        for key in ("updated_at", "last_save_source", "last_slot", "last_save_mode",
                    "last_save_timestamp", "source_kind"):
            value = payload.get(key)
            if value is not None and not isinstance(value, (str, int)):
                raise ManualTrackingError("État local invalide")
            result[key] = value
        result["synchronization_events"] = clean_events
        return result

    def _read_file(self, path: Path) -> dict:
        return self._validate(read_json(path))

    def load(self) -> dict:
        with self._lock:
            if not self.path.exists():
                return self._empty()
            try:
                return self._read_file(self.path)
            except (OSError, json.JSONDecodeError, ManualTrackingError):
                if self.backup_path.exists():
                    try:
                        return self._read_file(self.backup_path)
                    except (OSError, json.JSONDecodeError, ManualTrackingError):
                        pass
                raise ManualTrackingError(
                    f"L’état local est illisible. Une copie est conservée dans {self.path.parent}"
                )

    def update_sync(self, synchronization: object) -> dict:
        if not isinstance(synchronization, dict):
            raise ManualTrackingError("État de synchronisation invalide")
        with self._lock:
            current = self.load()
            candidate = {
                "last_save_source": synchronization.get("source_root"),
                "last_slot": synchronization.get("slot"),
                "last_save_mode": synchronization.get("save_mode"),
                "last_save_timestamp": synchronization.get("save_timestamp"),
                "source_kind": synchronization.get("source_kind"),
                "synchronization_events": synchronization.get("events", []),
            }
            if all(current.get(key) == value for key, value in candidate.items()):
                return current
            current.update(candidate)
            current["updated_at"] = datetime.now(timezone.utc).isoformat()
            clean = self._validate(current)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                try:
                    self._read_file(self.path)
                except (OSError, json.JSONDecodeError, ManualTrackingError):
                    pass
                else:
                    copy_valid_backup(self.path, self.backup_path)
            return atomic_write_json(self.path, clean)