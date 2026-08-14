from __future__ import annotations

import threading
import time
from typing import Callable


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

    def heartbeat(self) -> dict:
        with self._lock:
            self._last_activity = self.clock()
            self._seen_browser = True
            return {"active": True, "inactivity_seconds": self.inactivity_seconds}

    def request_shutdown(self) -> None:
        with self._lock:
            self._shutdown_requested = True

    def should_shutdown(self) -> bool:
        with self._lock:
            return self._shutdown_requested

    @property
    def has_browser(self) -> bool:
        with self._lock:
            return self._seen_browser