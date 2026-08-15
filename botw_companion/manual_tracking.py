from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import threading

from .persistence import (
    atomic_write_json,
    copy_valid_backup,
    migration_backup_path,
    read_json,
)
from .platforms import companion_data_dir


SCHEMA_VERSION = 2


class ManualTrackingError(ValueError):
    """Raised when a manual-tracking request is invalid or stale."""


def default_tracking_path() -> Path:
    return companion_data_dir() / "manual_tracking.json"


class ManualTrackingStore:
    """Small, thread-safe JSON store, kept entirely separate from BOTW saves."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_tracking_path()
        self.backup_path = self.path.with_suffix(".backup.json")
        self._lock = threading.RLock()

    @staticmethod
    def _empty() -> dict:
        return {"schema_version": SCHEMA_VERSION, "revision": 0, "updated_at": None, "entries": {}}

    @staticmethod
    def _validate(payload: object) -> dict:
        if not isinstance(payload, dict) or not isinstance(payload.get("entries"), dict):
            raise ManualTrackingError("Format de suivi manuel invalide")
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise ManualTrackingError("Version du suivi manuel non prise en charge")
        entries = {}
        for tracking_id, raw in payload["entries"].items():
            if not isinstance(tracking_id, str) or not tracking_id or len(tracking_id) > 300:
                raise ManualTrackingError("Identifiant de suivi invalide")
            if not isinstance(raw, dict) or not isinstance(raw.get("completed", False), bool):
                raise ManualTrackingError(f"État manuel invalide pour {tracking_id}")
            note = raw.get("note", "")
            if not isinstance(note, str) or len(note) > 1000:
                raise ManualTrackingError(f"Note manuelle invalide pour {tracking_id}")
            if raw.get("completed", False) or note.strip():
                entries[tracking_id] = {
                    "completed": raw.get("completed", False),
                    "note": note.strip(),
                    "updated_at": raw.get("updated_at"),
                }
        revision = payload.get("revision", 0)
        if not isinstance(revision, int) or revision < 0:
            raise ManualTrackingError("Révision de suivi invalide")
        return {
            "schema_version": SCHEMA_VERSION,
            "revision": revision,
            "updated_at": payload.get("updated_at"),
            "entries": entries,
        }

    @staticmethod
    def _migrate(payload: object) -> tuple[dict, int]:
        if not isinstance(payload, dict):
            raise ManualTrackingError("Format de suivi manuel invalide")
        source_version = payload.get("schema_version", 1)
        if not isinstance(source_version, int) or source_version < 1 or source_version > SCHEMA_VERSION:
            raise ManualTrackingError("Version du suivi manuel non prise en charge")
        migrated = dict(payload)
        if source_version == 1:
            migrated["schema_version"] = 2
        return migrated, source_version

    def _read_file(self, path: Path) -> tuple[dict, int]:
        migrated, source_version = self._migrate(read_json(path))
        return self._validate(migrated), source_version

    def load(self) -> dict:
        with self._lock:
            if not self.path.exists():
                return self._empty()
            try:
                payload, source_version = self._read_file(self.path)
            except ManualTrackingError as exc:
                if "Version" in str(exc):
                    raise
                payload = self._load_backup_or_raise()
                return payload
            except (OSError, json.JSONDecodeError):
                return self._load_backup_or_raise()
            if source_version < SCHEMA_VERSION:
                migration_backup = migration_backup_path(self.path, source_version)
                if not migration_backup.exists():
                    copy_valid_backup(self.path, migration_backup)
                atomic_write_json(self.path, payload)
            return payload

    def _load_backup_or_raise(self) -> dict:
        if self.backup_path.exists():
            try:
                return self._read_file(self.backup_path)[0]
            except (OSError, json.JSONDecodeError, ManualTrackingError):
                pass
        raise ManualTrackingError(
            f"Le suivi manuel est illisible. Une copie est conservée dans {self.path.parent}"
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

    @staticmethod
    def _check_revision(current: dict, expected_revision: object) -> None:
        if expected_revision is not None and expected_revision != current["revision"]:
            raise ManualTrackingError("Le suivi a changé dans une autre fenêtre; actualise puis réessaie")

    def update(self, tracking_id: str, completed: bool, note: str = "",
               expected_revision: int | None = None) -> dict:
        if not isinstance(tracking_id, str) or not tracking_id or len(tracking_id) > 300:
            raise ManualTrackingError("Identifiant de suivi invalide")
        if not isinstance(completed, bool) or not isinstance(note, str) or len(note) > 1000:
            raise ManualTrackingError("État de suivi invalide")
        with self._lock:
            current = self.load()
            self._check_revision(current, expected_revision)
            now = datetime.now(timezone.utc).isoformat()
            if completed or note.strip():
                current["entries"][tracking_id] = {
                    "completed": completed, "note": note.strip(), "updated_at": now,
                }
            else:
                current["entries"].pop(tracking_id, None)
            current.update(revision=current["revision"] + 1, updated_at=now)
            return self._write(current)

    def import_data(self, imported: object, mode: str = "merge",
                    expected_revision: int | None = None) -> dict:
        incoming = self._validate(self._migrate(imported)[0])
        if mode not in {"merge", "replace"}:
            raise ManualTrackingError("Mode d’import inconnu")
        with self._lock:
            current = self.load()
            self._check_revision(current, expected_revision)
            entries = dict(incoming["entries"]) if mode == "replace" else {
                **current["entries"], **incoming["entries"],
            }
            now = datetime.now(timezone.utc).isoformat()
            result = {
                "schema_version": SCHEMA_VERSION,
                "revision": current["revision"] + 1,
                "updated_at": now,
                "entries": entries,
            }
            return self._write(result)