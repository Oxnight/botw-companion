from __future__ import annotations

import json
import threading
import time
from typing import Callable
from urllib.error import URLError
from urllib.request import urlopen


APPLICATION_NAME = "BOTW Companion"


def probe_companion_server(port: int = 8765, timeout: float = 0.8,
                           opener=urlopen) -> dict | None:
    """Identifie le serveur local au lieu de faire confiance au seul port."""
    try:
        with opener(f"http://127.0.0.1:{port}/api/version", timeout=timeout) as response:
            if getattr(response, "status", 200) != 200:
                return None
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("application") != APPLICATION_NAME:
        return None
    if not isinstance(payload.get("version"), str):
        return None
    return payload


class WebLifecycle:
    """Tracks the local browser without treating a hidden tab as an exit.

    Browsers may heavily throttle a background tab while Ryujinx is in the
    foreground.  Heartbeats therefore remain diagnostic only: shutdown is an
    explicit action, or is handled by the macOS launcher when Ryujinx exits.
    """

    def __init__(self, inactivity_seconds: float = 300,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.inactivity_seconds = max(60.0, float(inactivity_seconds))
        self.clock = clock
        self._lock = threading.Lock()
        self._last_activity = self.clock()
        self._seen_browser = False
        self._shutdown_requested = False
        self._shutdown_reason: str | None = None

    def heartbeat(self) -> dict:
        with self._lock:
            self._last_activity = self.clock()
            self._seen_browser = True
            return {"active": True, "inactivity_seconds": self.inactivity_seconds}

    def request_shutdown(self, reason: str = "explicit") -> None:
        with self._lock:
            self._shutdown_requested = True
            self._shutdown_reason = reason

    def should_shutdown(self) -> bool:
        with self._lock:
            return self._shutdown_requested

    @property
    def has_browser(self) -> bool:
        with self._lock:
            return self._seen_browser

    @property
    def shutdown_reason(self) -> str | None:
        with self._lock:
            return self._shutdown_reason


class RyujinxLifecycleWatcher:
    """Surveille Ryujinx à faible fréquence sans dépendre du navigateur."""

    def __init__(self, is_running: Callable[[], bool],
                 request_shutdown: Callable[[str], None], *,
                 poll_seconds: float = 15.0,
                 close_grace_seconds: float = 30.0,
                 resume_gap_seconds: float = 60.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.is_running = is_running
        self.request_shutdown = request_shutdown
        self.poll_seconds = max(1.0, float(poll_seconds))
        self.close_grace_seconds = max(self.poll_seconds, float(close_grace_seconds))
        self.resume_gap_seconds = max(self.poll_seconds * 3, float(resume_gap_seconds))
        self.clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._seen_running = False
        self._missing_since: float | None = None
        self._last_check: float | None = None
        self._state = "initialisation"
        self._error: str | None = None

    def check_once(self) -> bool:
        now = self.clock()
        resumed = self._last_check is not None and now - self._last_check >= self.resume_gap_seconds
        self._last_check = now
        try:
            running = bool(self.is_running())
        except OSError as exc:
            self._state = "erreur_detection"
            self._error = str(exc)
            self._missing_since = None
            return False
        self._error = None
        if running:
            self._seen_running = True
            self._missing_since = None
            self._state = "ryujinx_actif"
            return False
        if not self._seen_running:
            self._state = "attente_ryujinx"
            return False
        if resumed:
            self._missing_since = now
            self._state = "reprise_apres_veille"
            return False
        if self._missing_since is None:
            self._missing_since = now
            self._state = "fermeture_a_confirmer"
            return False
        if now - self._missing_since < self.close_grace_seconds:
            self._state = "fermeture_a_confirmer"
            return False
        self._state = "ryujinx_ferme"
        self.request_shutdown("ryujinx_ferme")
        return True

    def _run(self) -> None:
        if self.check_once():
            return
        while not self._stop.wait(self.poll_seconds):
            if self.check_once():
                return

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="botw-companion-ryujinx-watcher",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=min(2.0, self.poll_seconds + 0.1))
        self._thread = None

    def status(self) -> dict:
        return {
            "enabled": True,
            "state": self._state,
            "seen_running": self._seen_running,
            "missing_since": self._missing_since,
            "last_check": self._last_check,
            "error": self._error,
            "poll_seconds": self.poll_seconds,
            "close_grace_seconds": self.close_grace_seconds,
        }