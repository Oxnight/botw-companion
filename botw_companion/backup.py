from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager, ExitStack
import base64
import binascii
import threading

from .manual_tracking import ManualTrackingError, ManualTrackingStore
from .persistence import atomic_write_json, read_json, restore_bytes, _sync_directory
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
        self.journal_path = tracking.path.with_name(f".{tracking.path.stem}.restore-journal.json")

    def _paths(self):
        return tuple(path for store in (self.tracking, self.routes, self.preferences)
                     for path in (store.path, store.backup_path))

    def _recover(self) -> None:
        if not self.journal_path.exists():
            return
        paths = self._paths()
        try:
            journal = read_json(self.journal_path)
            if (not isinstance(journal, dict) or type(journal.get("schema_version")) is not int
                    or journal.get("schema_version") != 1
                    or journal.get("paths") != [str(path.resolve()) for path in paths]
                    or not isinstance(journal.get("contents"), list)
                    or len(journal["contents"]) != len(paths)):
                raise ValueError("Invalid restore journal")
            contents = [None if content is None else base64.b64decode(content, validate=True)
                        for content in journal["contents"]]
        except (ValueError, TypeError, binascii.Error) as exc:
            raise ManualTrackingError("Restauration interrompue : journal de récupération invalide") from exc
        # Use the configured store paths, never a destination supplied by JSON.
        # Keep the journal until every old primary and recovery copy is durable.
        for path, content in zip(paths, contents):
            restore_bytes(path, content)
        self._remove_journal()

    def _remove_journal(self):
        self.journal_path.unlink()
        _sync_directory(self.journal_path.parent)

    def recover_pending(self) -> None:
        with self._transaction():
            self._recover()

    def export(self) -> dict:
        with self._transaction():
            self._recover()
            return {
                "schema_version": SCHEMA_VERSION,
                "application": "BOTW Companion",
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "manual_tracking": self.tracking.load(),
                "route_sessions": self.routes.load(),
                "preferences": self.preferences.load(),
            }

    @contextmanager
    def _transaction(self):
        # The HTTP server can modify each store from another tab. Keep a fixed
        # lock order for exports and restores, including rollback. Store locks
        # are reentrant because their public methods acquire them again.
        with self._lock, ExitStack() as locks:
            for store in (self.tracking, self.routes, self.preferences):
                locks.enter_context(store._lock)
            yield

    def restore(self, payload: object) -> dict:
        if not isinstance(payload, dict) or payload.get("application") != "BOTW Companion":
            raise ManualTrackingError("Sauvegarde générale invalide")
        version = payload.get("schema_version", 1)
        if type(version) is not int or version not in {1, SCHEMA_VERSION}:
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
        with self._transaction():
            self._recover()
            stores = (self.tracking, self.routes, self.preferences)
            snapshots = {
                path: path.read_bytes() if path.exists() else None
                for store in stores
                for path in (store.path, store.backup_path)
            }
            atomic_write_json(self.journal_path, {
                "schema_version": 1,
                "paths": [str(path.resolve()) for path in snapshots],
                "contents": [base64.b64encode(content).decode("ascii") if content is not None else None
                             for content in snapshots.values()],
            })
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
                self._remove_journal()
            except Exception:
                self._recover()
                raise
        return {
            "schema_version": SCHEMA_VERSION,
            "manual_tracking": restored_tracking,
            "route_sessions": restored_routes,
            "preferences": restored_preferences,
        }
