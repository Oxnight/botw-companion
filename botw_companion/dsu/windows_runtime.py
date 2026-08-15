from __future__ import annotations

import ctypes
from ctypes import wintypes
import os


EVENT_MODIFY_STATE = 0x0002
STOP_EVENT_PREFIX = "Local\\BOTWCompanion.JoyConDSU.Stop."


def stop_event_name(process_id: int) -> str:
    if process_id <= 0:
        raise ValueError("Identifiant de processus JoyConDSU invalide")
    return f"{STOP_EVENT_PREFIX}{process_id}"


def signal_stop_event(process_id: int, *, kernel32=None) -> bool:
    """Demande au moteur Windows de sortir proprement de sa boucle SDL/DSU."""
    if kernel32 is None:
        if os.name != "nt":
            return False
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenEventW.argtypes = (
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        )
        kernel32.OpenEventW.restype = wintypes.HANDLE
        kernel32.SetEvent.argtypes = (wintypes.HANDLE,)
        kernel32.SetEvent.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenEventW(
        EVENT_MODIFY_STATE,
        False,
        stop_event_name(process_id),
    )
    if not handle:
        return False
    try:
        return bool(kernel32.SetEvent(handle))
    finally:
        kernel32.CloseHandle(handle)