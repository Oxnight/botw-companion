"""Persist a bounded, single-tab handoff across an assisted update."""
from __future__ import annotations

import json
from pathlib import Path
import re
import secrets
import threading
import time

from .persistence import atomic_write_json
from .platforms import companion_data_dir
from .lifecycle import open_loopback
from urllib.request import Request


class BrowserHandoff:
    def __init__(self, path: Path | None = None, *, clock=time.time):
        self.path = path or companion_data_dir() / "browser-handoff.json"
        self.clock = clock
        self.lock = threading.Lock()

    def _read(self, port: int) -> dict | None:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
            if (not isinstance(state, dict) or state.get("port") != port
                    or not all(key in state for key in ("id", "client_id", "old_token", "claimed_by", "claimed_token"))
                    or not 0 <= self.clock() - state["created_at"] <= 600):
                return None
            return state
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def prepare(self, client_id: str, port: int, old_token: str) -> dict:
        if not isinstance(client_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", client_id):
            raise ValueError("Invalid browser handoff identifier")
        state = {"id": secrets.token_urlsafe(24), "client_id": client_id,
                 "port": port, "old_token": old_token,
                 "created_at": self.clock(), "claimed_by": None, "claimed_token": None}
        with self.lock:
            atomic_write_json(self.path, state)
        return {"id": state["id"], "client_id": client_id}

    def cancel(self) -> None:
        with self.lock:
            self.path.unlink(missing_ok=True)

    def status(self, port: int, token: str) -> dict | None:
        with self.lock:
            state = self._read(port)
        if (state is None or state["old_token"] == token
                or state["claimed_token"] not in (None, token)):
            return None
        return {key: state[key] for key in ("id", "client_id", "claimed_by")}

    def claim(self, port: int, token: str, handoff_id: str, client_id: str) -> dict | None:
        if not isinstance(client_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,80}", client_id):
            raise ValueError("Invalid browser handoff identifier")
        with self.lock:
            state = self._read(port)
            if (state is None or state["old_token"] == token or state["id"] != handoff_id
                    or state["claimed_token"] not in (None, token)):
                return None
            if state["claimed_by"] is None and state["client_id"] in (None, client_id):
                state["claimed_by"] = client_id
                state["claimed_token"] = token
                atomic_write_json(self.path, state)
            return {key: state[key] for key in ("id", "client_id", "claimed_by")}

    def release(self, port: int, token: str) -> None:
        """Allow a fresh tab if the original tab did not return in time."""
        with self.lock:
            state = self._read(port)
            if state is not None and state["old_token"] != token and state["claimed_by"] is None:
                state["client_id"] = None
                atomic_write_json(self.path, state)


def await_browser_handoff(port: int, identity: dict, *, opener=open_loopback,
                          timeout=8.0, clock=time.monotonic, sleep=time.sleep) -> bool:
    """Acknowledge reuse before suppressing the launcher's normal browser open."""
    state = identity.get("browser_handoff")
    if not isinstance(state, dict):
        return False
    token = identity.get("session_token")
    handoff_id = state.get("id")
    deadline = clock() + timeout
    while True:
        if state.get("claimed_by"):
            return True
        if clock() >= deadline:
            break
        sleep(.1)
        try:
            with opener(f"http://127.0.0.1:{port}/api/version", timeout=.5) as response:
                current = json.loads(response.read())
            state = current.get("browser_handoff")
            if (current.get("application") != "BOTW Companion"
                    or current.get("session_token") != token
                    or not isinstance(state, dict) or state.get("id") != handoff_id):
                return False
        except (OSError, ValueError, TypeError):
            continue
    try:
        with opener(Request(f"http://127.0.0.1:{port}/api/browser/release", data=b"",
                            headers={"X-BOTW-Session-Token": token or ""}, method="POST"), timeout=1):
            pass
    except OSError:
        pass
    return False
