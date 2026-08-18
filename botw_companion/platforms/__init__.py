from __future__ import annotations

from pathlib import Path
from hashlib import sha256
import os
import platform
import shutil
import xml.etree.ElementTree as ET
from typing import Callable, Mapping

from . import linux, macos, windows


Environment = Mapping[str, str]
Which = Callable[[str], str | None]


class LocalInstanceGuard:
    """Le socket assure déjà l'instance unique hors Windows."""

    def acquire(self) -> bool:
        return True

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()


class LocalShutdownNotifier:
    def close(self) -> None:
        pass


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


def platform_metadata(system: str | None = None, *,
                      environ: Environment | None = None,
                      home: Path | None = None) -> dict[str, str]:
    resolved = system_name(system)
    data_root = companion_data_dir(system=resolved, environ=environ, home=home)
    platform_key = platform_id(resolved)
    presentation = {
        "macos": {
            "installation_label": "application macOS",
            "native_dsu_engine": "JoyConDSU",
            "relaunch_hint": (
                "Tu peux fermer cet onglet. Relance BOTW Companion depuis "
                "son icône dans le Dock ou depuis le Finder."
            ),
            "shortcut_modifier": "⌘",
        },
        "windows": {
            "installation_label": "application Windows",
            "native_dsu_engine": "JoyConDSU.exe",
            "relaunch_hint": (
                "Tu peux fermer cet onglet. Relance BOTW Companion depuis "
                "son raccourci Windows ou son dossier d’installation."
            ),
            "shortcut_modifier": "Ctrl",
        },
        "linux": {
            "installation_label": "application Linux",
            "native_dsu_engine": "JoyConDSU",
            "relaunch_hint": (
                "Tu peux fermer cet onglet. Relance BOTW Companion depuis "
                "ton lanceur ou son dossier d’installation."
            ),
            "shortcut_modifier": "Ctrl",
        },
    }.get(platform_key, {
        "installation_label": "application locale",
        "native_dsu_engine": "JoyConDSU",
        "relaunch_hint": (
            "Tu peux fermer cet onglet. Relance BOTW Companion pour "
            "redémarrer l’application."
        ),
        "shortcut_modifier": "Ctrl",
    })
    return {
        "id": platform_key,
        "label": platform_label(resolved),
        "system": resolved,
        "installation_label": presentation["installation_label"],
        "native_dsu_engine": presentation["native_dsu_engine"],
        "relaunch_hint": presentation["relaunch_hint"],
        "shortcut_modifier": presentation["shortcut_modifier"],
        "data_directory": str(data_root),
        "dsu_log_path": str(data_root / "joycon-dsu.log"),
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



def _cemu_mlc_from_settings(data_dir: Path) -> list[Path]:
    settings = data_dir / "settings.xml"
    if not settings.is_file():
        return []
    try:
        root = ET.parse(settings).getroot()
    except (OSError, ET.ParseError):
        return []
    value = root.findtext("mlc_path")
    if not value or not value.strip():
        return []
    candidate = Path(value.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = data_dir / candidate
    return [candidate]


def cemu_save_roots(*, system: str | None = None,
                    environ: Environment | None = None,
                    home: Path | None = None,
                    which: Which = shutil.which) -> list[Path]:
    values = _environment(environ)
    resolved = system_name(system)
    root = _home(home)
    data_dirs: list[Path] = []
    direct_mlc = values.get("CEMU_MLC_PATH") or values.get("BOTW_CEMU_MLC_PATH")
    if direct_mlc:
        data_dirs.append(Path(direct_mlc).expanduser())
    if resolved == "Darwin":
        app_dirs = macos.cemu_data_dirs(values, root)
    elif resolved == "Windows":
        app_dirs = windows.cemu_data_dirs(values, root, which)
    else:
        app_dirs = []
    mlc_roots: list[Path] = list(data_dirs)
    for data_dir in app_dirs:
        mlc_roots.extend(_cemu_mlc_from_settings(data_dir))
        mlc_roots.append(data_dir / "mlc01")
    return _unique([mlc / "usr" / "save" for mlc in mlc_roots])


def cemu_is_running(*, system: str | None = None,
                    process_names: Callable[[], set[str]] | None = None,
                    environ: Environment | None = None) -> bool:
    values = _environment(environ)
    resolved = system_name(system)
    if resolved == "Windows":
        return windows.cemu_is_running(process_names, values)
    if resolved == "Darwin":
        return macos.cemu_is_running(process_names, values)
    return False


def server_instance_guard(*, system: str | None = None,
                          environ: Environment | None = None,
                          home: Path | None = None,
                          mutex_factory=None):
    """Retourne un verrou par utilisateur pour l'unique serveur Windows."""
    resolved = system_name(system)
    if resolved != "Windows":
        return LocalInstanceGuard()
    data_root = companion_data_dir(system=resolved, environ=environ, home=home)
    identity = sha256(str(data_root).casefold().encode("utf-8")).hexdigest()[:16]
    name = f"Local\\BOTWCompanion.Server.{identity}"
    factory = mutex_factory or windows.WindowsNamedMutex
    return factory(name)


def ryujinx_is_running(*, system: str | None = None,
                       process_names: Callable[[], set[str]] | None = None,
                       environ: Environment | None = None) -> bool:
    values = _environment(environ)
    resolved = system_name(system)
    if resolved == "Windows":
        return windows.ryujinx_is_running(process_names, values)
    if resolved == "Darwin":
        return macos.ryujinx_is_running(process_names, values)
    return False


def system_shutdown_notifier(callback: Callable[[str], None], *,
                             system: str | None = None,
                             windows_factory=None):
    if system_name(system) != "Windows":
        return LocalShutdownNotifier()
    factory = windows_factory or windows.WindowsConsoleShutdownHandler
    return factory(callback)