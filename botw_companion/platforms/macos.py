from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Callable, Mapping


def companion_data_dir(_environ: Mapping[str, str], home: Path) -> Path:
    return home / "Library" / "Application Support" / "BOTW Companion"


def ryujinx_save_roots(_environ: Mapping[str, str], home: Path) -> list[Path]:
    return [
        home / "Library" / "Application Support" / "Ryujinx" / "bis" / "user" / "save",
        home / ".config" / "Ryujinx" / "bis" / "user" / "save",
    ]

def cemu_data_dirs(environ: Mapping[str, str], home: Path) -> list[Path]:
    override = environ.get("CEMU_DATA_DIR") or environ.get("BOTW_CEMU_DATA_DIR")
    roots = [Path(override).expanduser()] if override else []
    roots.extend([
        home / "Library" / "Application Support" / "Cemu",
        home / ".local" / "share" / "Cemu",
    ])
    return roots


def process_names() -> set[str]:
    try:
        completed = subprocess.run(
            ["/bin/ps", "-axo", "comm="],
            check=False, capture_output=True, text=True, timeout=2.0,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    return {Path(line.strip()).name.casefold() for line in completed.stdout.splitlines() if line.strip()}


def configured_process_names(base: set[str], env_name: str, environ: Mapping[str, str]) -> set[str]:
    extras = {name.strip().casefold() for name in environ.get(env_name, "").replace(",", ";").split(";") if name.strip()}
    return {name.casefold() for name in base} | extras


def ryujinx_is_running(names: Callable[[], set[str]] | None, environ: Mapping[str, str]) -> bool:
    current = names() if names is not None else process_names()
    expected = configured_process_names({"Ryujinx", "Ryujinx.Ava"}, "BOTW_RYUJINX_PROCESS_NAMES", environ)
    return bool(expected.intersection(name.casefold() for name in current))


def cemu_is_running(names: Callable[[], set[str]] | None, environ: Mapping[str, str]) -> bool:
    current = names() if names is not None else process_names()
    expected = configured_process_names({"Cemu", "Cemu_bin"}, "BOTW_CEMU_PROCESS_NAMES", environ)
    return bool(expected.intersection(name.casefold() for name in current))