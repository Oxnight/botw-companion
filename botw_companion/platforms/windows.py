from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
from typing import Callable, Mapping


Which = Callable[[str], str | None]
RYUJINX_PROCESS_NAMES = frozenset({"ryujinx.exe", "ryujinx.ava.exe"})
TH32CS_SNAPPROCESS = 0x00000002
ERROR_ALREADY_EXISTS = 183
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
WINDOWS_SHUTDOWN_EVENTS = frozenset({0, 1, 2, 5, 6})


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class WindowsNamedMutex:
    """Verrou Win32 conservé pendant toute la vie d'une instance serveur."""

    def __init__(self, name: str, *, kernel32=None, get_last_error=None) -> None:
        if kernel32 is None:
            if os.name != "nt":
                raise OSError("Les mutex nommés Windows ne sont disponibles que sous Windows")
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel32.CloseHandle.restype = wintypes.BOOL
        self.name = name
        self._kernel32 = kernel32
        self._get_last_error = get_last_error or ctypes.get_last_error
        self._handle = None

    def acquire(self) -> bool:
        if self._handle is not None:
            return True
        handle = self._kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            raise ctypes.WinError(self._get_last_error())
        if self._get_last_error() == ERROR_ALREADY_EXISTS:
            self._kernel32.CloseHandle(handle)
            return False
        self._handle = handle
        return True

    def close(self) -> None:
        if self._handle is not None:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("Une instance de BOTW Companion fonctionne déjà")
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()


class WindowsConsoleShutdownHandler:
    """Convertit les événements console, fermeture et session en arrêt propre."""

    def __init__(self, callback: Callable[[str], None], *, kernel32=None) -> None:
        self.callback = callback
        self._kernel32 = kernel32
        self._registered = False
        self._native_callback = None
        if self._kernel32 is None:
            if os.name != "nt":
                return
            self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        callback_type = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(
            wintypes.BOOL,
            wintypes.DWORD,
        )
        self._native_callback = callback_type(self._handle)
        if kernel32 is None:
            self._kernel32.SetConsoleCtrlHandler.argtypes = (callback_type, wintypes.BOOL)
            self._kernel32.SetConsoleCtrlHandler.restype = wintypes.BOOL
        self._registered = bool(self._kernel32.SetConsoleCtrlHandler(
            self._native_callback,
            True,
        ))

    def _handle(self, control_type: int) -> bool:
        if control_type not in WINDOWS_SHUTDOWN_EVENTS:
            return False
        self.callback(f"windows_control_{control_type}")
        return True

    def close(self) -> None:
        if self._registered and self._kernel32 is not None and self._native_callback is not None:
            self._kernel32.SetConsoleCtrlHandler(self._native_callback, False)
        self._registered = False


def running_process_names(*, kernel32=None) -> set[str]:
    """Énumère les exécutables sans lancer tasklist ni PowerShell."""
    if kernel32 is None:
        if os.name != "nt":
            return set()
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
        kernel32.Process32FirstW.restype = wintypes.BOOL
        kernel32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
        kernel32.Process32NextW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot in (None, 0, INVALID_HANDLE_VALUE):
        return set()
    names: set[str] = set()
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        available = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while available:
            names.add(str(entry.szExeFile).casefold())
            available = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return names


def ryujinx_is_running(process_names: Callable[[], set[str]] | None = None) -> bool:
    names = process_names() if process_names is not None else running_process_names()
    return bool(RYUJINX_PROCESS_NAMES.intersection(name.casefold() for name in names))


def _environment_path(environ: Mapping[str, str], name: str, fallback: Path) -> Path:
    value = environ.get(name)
    return Path(value).expanduser() if value else fallback


def companion_data_dir(environ: Mapping[str, str], home: Path) -> Path:
    local = _environment_path(environ, "LOCALAPPDATA", home / "AppData" / "Local")
    return local / "BOTW Companion"


def _known_executables(environ: Mapping[str, str], home: Path,
                       which: Which) -> list[Path]:
    executables: list[Path] = []
    for name in ("RYUJINX_EXECUTABLE", "RYUJINX_EXE"):
        if environ.get(name):
            executables.append(Path(environ[name]).expanduser())
    for name in ("Ryujinx.exe", "Ryujinx.Ava.exe"):
        resolved = which(name)
        if resolved:
            executables.append(Path(resolved))
    local = _environment_path(environ, "LOCALAPPDATA", home / "AppData" / "Local")
    program_files = _environment_path(environ, "PROGRAMFILES", Path("C:/Program Files"))
    for directory in (
        local / "Programs" / "Ryujinx",
        local / "Ryujinx",
        program_files / "Ryujinx",
    ):
        executables.extend((directory / "Ryujinx.exe", directory / "Ryujinx.Ava.exe"))
    return executables


def ryujinx_save_roots(environ: Mapping[str, str], home: Path,
                       which: Which) -> list[Path]:
    roaming = _environment_path(environ, "APPDATA", home / "AppData" / "Roaming")
    roots = [roaming / "Ryujinx" / "bis" / "user" / "save"]
    for executable in _known_executables(environ, home, which):
        roots.append(executable.parent / "portable" / "bis" / "user" / "save")
    return roots