from __future__ import annotations

from pathlib import Path
import os
import platform
import shutil
from typing import Callable, Mapping

from . import linux, macos, windows


Environment = Mapping[str, str]
Which = Callable[[str], str | None]


def system_name(system: str | None = None) -> str:
    return system or platform.system()


def platform_id(system: str | None = None) -> str:
    return {
        "Darwin": "macos",
        "Windows": "windows",
        "Linux": "linux",
    }.get(system_name(system), "other")


def platform_label(system: str | None = None) -> str:
    return {
        "macos": "macOS",
        "windows": "Windows",
        "linux": "Linux",
    }.get(platform_id(system), system_name(system) or "Système inconnu")


def platform_metadata(system: str | None = None) -> dict[str, str]:
    resolved = system_name(system)
    return {
        "id": platform_id(resolved),
        "label": platform_label(resolved),
        "system": resolved,
    }


def _environment(environ: Environment | None) -> Environment:
    return os.environ if environ is None else environ


def _home(home: Path | None) -> Path:
    return Path.home() if home is None else Path(home)


def _unique(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = os.path.normcase(os.path.normpath(str(path.expanduser())))
        if key not in seen:
            seen.add(key)
            result.append(path.expanduser())
    return result


def companion_data_dir(*, system: str | None = None,
                       environ: Environment | None = None,
                       home: Path | None = None) -> Path:
    values = _environment(environ)
    override = values.get("BOTW_COMPANION_DATA_DIR")
    if override:
        return Path(override).expanduser()
    resolved = system_name(system)
    root = _home(home)
    if resolved == "Darwin":
        return macos.companion_data_dir(values, root)
    if resolved == "Windows":
        return windows.companion_data_dir(values, root)
    return linux.companion_data_dir(values, root)


def ryujinx_save_roots(*, system: str | None = None,
                       environ: Environment | None = None,
                       home: Path | None = None,
                       which: Which = shutil.which) -> list[Path]:
    values = _environment(environ)
    resolved = system_name(system)
    root = _home(home)
    candidates: list[Path] = []
    override = values.get("RYUJINX_DATA_DIR")
    if override:
        candidates.append(Path(override).expanduser() / "bis" / "user" / "save")
    if resolved == "Darwin":
        candidates.extend(macos.ryujinx_save_roots(values, root))
    elif resolved == "Windows":
        candidates.extend(windows.ryujinx_save_roots(values, root, which))
    else:
        candidates.extend(linux.ryujinx_save_roots(values, root))
    return _unique(candidates)