from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import threading
import uuid

from .manual_tracking import ManualTrackingError, default_tracking_path


SCHEMA_VERSION = 2
MAX_SESSIONS = 100
MAX_ENTRIES = 1000


def default_routes_path() -> Path:
    return default_tracking_path().with_name("route_sessions.json")


class RouteSessionStore:
    """Persistent, revision-protected route sessions independent from saves."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_routes_path()
        self.backup_path = self.path.with_suffix(".backup.json")
        self._lock = threading.RLock()

    @staticmethod
    def _new_id() -> str:
        return f"session-{uuid.uuid4().hex[:16]}"

    @classmethod
    def _empty(cls) -> dict:
        session_id = cls._new_id()
        now = datetime.now(timezone.utc).isoformat()
        return {
            "schema_version": SCHEMA_VERSION, "revision": 0, "updated_at": None,
            "active_session_id": session_id,
            "sessions": {session_id: {
                "id": session_id, "name": "Session BOTW", "start": None,
                "strategy": "distance", "entries": [],
                "created_at": now, "updated_at": now,
            }},
        }

    @staticmethod
    def _validate_point(raw: object) -> dict | None:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ManualTrackingError("Point de départ invalide")
        try:
            x, z = float(raw["x"]), float(raw["z"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ManualTrackingError("Coordonnées de départ invalides") from exc
        label = raw.get("label", "Point personnalisé")
        if not isinstance(label, str) or len(label) > 300:
            raise ManualTrackingError("Libellé de départ invalide")
        return {"x": x, "z": z, "label": label.strip() or "Point personnalisé"}

    @staticmethod
    def _validate_entry(raw: object) -> dict:
        if not isinstance(raw, dict):
            raise ManualTrackingError("Étape d’itinéraire invalide")
        tracking_id = raw.get("tracking_id")
        if not isinstance(tracking_id, str) or not tracking_id or len(tracking_id) > 300:
            raise ManualTrackingError("Identifiant d’étape invalide")
        snapshot = raw.get("snapshot") or {}
        if not isinstance(snapshot, dict):
            raise ManualTrackingError("Copie d’étape invalide")
        clean_snapshot = {}
        for key in ("name", "category", "region", "content_origin"):
            value = snapshot.get(key)
            if value is not None:
                if not isinstance(value, str) or len(value) > 500:
                    raise ManualTrackingError("Métadonnée d’étape invalide")
                clean_snapshot[key] = value
        for key in ("x", "z"):
            value = snapshot.get(key)
            if value is not None:
                try:
                    clean_snapshot[key] = float(value)
                except (TypeError, ValueError) as exc:
                    raise ManualTrackingError("Coordonnée d’étape invalide") from exc
        return {"tracking_id": tracking_id, "locked": bool(raw.get("locked", False)),
                "snapshot": clean_snapshot}

    @classmethod
    def _validate_session(cls, raw: object, fallback_id: str | None = None) -> dict:
        if not isinstance(raw, dict):
            raise ManualTrackingError("Session d’itinéraire invalide")
        session_id = raw.get("id") or fallback_id
        name = raw.get("name", "Session BOTW")
        entries = raw.get("entries", [])
        strategy = raw.get("strategy", "distance")
        if not isinstance(session_id, str) or not session_id or len(session_id) > 100:
            raise ManualTrackingError("Identifiant de session invalide")
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ManualTrackingError("Nom de session invalide")
        if strategy not in {"distance", "region", "teleport"}:
            raise ManualTrackingError("Stratégie d’itinéraire inconnue")
        if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
            raise ManualTrackingError(f"Une session est limitée à {MAX_ENTRIES} étapes")
        clean_entries, seen = [], set()
        for entry in entries:
            clean = cls._validate_entry(entry)
            if clean["tracking_id"] in seen:
                raise ManualTrackingError("Une session ne peut pas contenir deux fois la même étape")
            seen.add(clean["tracking_id"])
            clean_entries.append(clean)
        return {
            "id": session_id, "name": name.strip(), "start": cls._validate_point(raw.get("start")),
            "strategy": strategy, "entries": clean_entries,
            "created_at": raw.get("created_at"), "updated_at": raw.get("updated_at"),
        }

    @classmethod
    def _validate(cls, payload: object) -> dict:
        if not isinstance(payload, dict) or not isinstance(payload.get("sessions"), dict):
            raise ManualTrackingError("Format des itinéraires invalide")
        if len(payload["sessions"]) > MAX_SESSIONS:
            raise ManualTrackingError(f"Le planificateur est limité à {MAX_SESSIONS} sessions")
        sessions = {sid: cls._validate_session(raw, sid) for sid, raw in payload["sessions"].items()}
        if not sessions:
            raise ManualTrackingError("Au moins une session est requise")
        active = payload.get("active_session_id")
        if active not in sessions:
            active = next(iter(sessions))
        revision = payload.get("revision", 0)
        if not isinstance(revision, int) or revision < 0:
            raise ManualTrackingError("Révision des itinéraires invalide")
        return {"schema_version": SCHEMA_VERSION, "revision": revision,
                "updated_at": payload.get("updated_at"), "active_session_id": active,
                "sessions": sessions}

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
                    f"Les itinéraires sont illisibles. Une copie est conservée dans {self.path.parent}"
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

    def replace(self, incoming: object, expected_revision: int | None = None) -> dict:
        clean = self._validate(incoming)
        with self._lock:
            current = self.load()
            if expected_revision is not None and expected_revision != current["revision"]:
                raise ManualTrackingError("Les itinéraires ont changé dans une autre fenêtre; actualise puis réessaie")
            now = datetime.now(timezone.utc).isoformat()
            clean.update(revision=current["revision"] + 1, updated_at=now)
            for session in clean["sessions"].values():
                session["created_at"] = session["created_at"] or now
                session["updated_at"] = now
            return self._write(clean)

    def import_session(self, raw: object, expected_revision: int | None = None) -> dict:
        if isinstance(raw, dict) and isinstance(raw.get("steps"), list):
            raw = {"name": raw.get("name", "Session importée"), "start": raw.get("start"),
                   "strategy": raw.get("strategy", "distance"),
                   "entries": [{"tracking_id": step.get("tracking_id"),
                                "locked": step.get("locked", False),
                                "snapshot": {key: step.get(key) for key in
                                             ("name", "category", "region", "x", "z", "content_origin")
                                             if step.get(key) is not None}}
                               for step in raw["steps"]]}
        new_id = self._new_id()
        session = self._validate_session({**raw, "id": new_id}, new_id) if isinstance(raw, dict) else self._validate_session(raw, new_id)
        with self._lock:
            current = self.load()
            if expected_revision is not None and expected_revision != current["revision"]:
                raise ManualTrackingError("Les itinéraires ont changé dans une autre fenêtre; actualise puis réessaie")
            if len(current["sessions"]) >= MAX_SESSIONS:
                raise ManualTrackingError(f"Le planificateur est limité à {MAX_SESSIONS} sessions")
            current["sessions"][new_id] = session
            current["active_session_id"] = new_id
            return self.replace(current, current["revision"])