from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import threading


SCHEMA_VERSION = 1


class ManualTrackingError(ValueError):
    """Raised when a manual-tracking request is invalid or stale."""


def default_tracking_path() -> Path:
    override = os.environ.get("BOTW_COMPANION_DATA_DIR")
    if override:
        root = Path(override).expanduser()
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "BOTW Companion"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "botw-companion"
    return root / "manual_tracking.json"


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

    def _read_file(self, path: Path) -> dict:
        return self._validate(json.loads(path.read_text(encoding="utf-8")))

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
                shutil.copy2(self.path, self.backup_path)
        temporary = self.path.with_suffix(".tmp")
        data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)
        return deepcopy(payload)

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
        incoming = self._validate(imported)
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