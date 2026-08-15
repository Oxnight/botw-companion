from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import threading

from .manual_tracking import ManualTrackingError, ManualTrackingStore
from .persistence import restore_bytes
from .preferences import PreferenceStore
from .route_sessions import RouteSessionStore


SCHEMA_VERSION = 2


class CompanionBackup:
    def __init__(self, tracking: ManualTrackingStore, routes: RouteSessionStore,
                 preferences: PreferenceStore):
        self.tracking = tracking
        self.routes = routes
        self.preferences = preferences
        self._lock = threading.RLock()

    def export(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "application": "BOTW Companion",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "manual_tracking": self.tracking.load(),
            "route_sessions": self.routes.load(),
            "preferences": self.preferences.load(),
        }

    def restore(self, payload: object) -> dict:
        if not isinstance(payload, dict) or payload.get("application") != "BOTW Companion":
            raise ManualTrackingError("Sauvegarde générale invalide")
        version = payload.get("schema_version", 1)
        if version not in {1, SCHEMA_VERSION}:
            raise ManualTrackingError("Version de sauvegarde générale non prise en charge")
        tracking = self.tracking._validate(
            self.tracking._migrate(payload.get("manual_tracking"))[0]
        )
        routes = self.routes._validate(
            self.routes._migrate(payload.get("route_sessions"))[0]
        )
        preferences = self.preferences._validate(
            payload.get("preferences", self.preferences._empty())
        )
        with self._lock:
            stores = (self.tracking, self.routes, self.preferences)
            snapshots = {
                store.path: store.path.read_bytes() if store.path.exists() else None
                for store in stores
            }
            try:
                current_tracking = self.tracking.load()
                current_routes = self.routes.load()
                current_preferences = self.preferences.load()
                restored_tracking = self.tracking.import_data(
                    tracking, mode="replace", expected_revision=current_tracking["revision"]
                )
                restored_routes = self.routes.replace(routes, current_routes["revision"])
                restored_preferences = self.preferences.replace(
                    preferences, current_preferences["revision"]
                )
            except Exception:
                for path, content in snapshots.items():
                    restore_bytes(Path(path), content)
                raise
        return {
            "schema_version": SCHEMA_VERSION,
            "manual_tracking": restored_tracking,
            "route_sessions": restored_routes,
            "preferences": restored_preferences,
        }