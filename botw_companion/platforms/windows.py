from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping


Which = Callable[[str], str | None]


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