from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import platform
import subprocess
from typing import Callable, Mapping

from .platforms import cemu_save_roots, ryujinx_save_roots
from .platforms import cemu_is_running, ryujinx_is_running


@dataclass(frozen=True)
class EmulatorBackend:
    id: str
    label: str


RYUJINX = EmulatorBackend("ryujinx", "Ryujinx")
CEMU = EmulatorBackend("cemu", "Cemu")


def emulator_save_roots(emulator: str | None = None, *, system: str | None = None,
                        environ: Mapping[str, str] | None = None,
                        home: Path | None = None,
                        which: Callable[[str], str | None] | None = None) -> list[tuple[EmulatorBackend, Path]]:
    """Retourne les racines de sauvegarde connues dans un ordre déterministe.

    Si aucun émulateur n'est imposé, les deux backends sont inspectés. Le choix
    final de la sauvegarde se fait ensuite sur l'horodatage interne BOTW, pas
    sur cet ordre.
    """
    kwargs = {"system": system, "environ": environ, "home": home}
    if which is not None:
        kwargs["which"] = which
    result: list[tuple[EmulatorBackend, Path]] = []
    requested = emulator.casefold() if emulator else None
    if requested in (None, RYUJINX.id):
        result.extend((RYUJINX, path) for path in ryujinx_save_roots(**kwargs))
    if requested in (None, CEMU.id):
        result.extend((CEMU, path) for path in cemu_save_roots(**kwargs))
    return result


def running_emulators(*, system: str | None = None,
                      process_names: Callable[[], set[str]] | None = None,
                      environ: Mapping[str, str] | None = None) -> list[EmulatorBackend]:
    result: list[EmulatorBackend] = []
    if ryujinx_is_running(system=system, process_names=process_names, environ=environ):
        result.append(RYUJINX)
    if cemu_is_running(system=system, process_names=process_names, environ=environ):
        result.append(CEMU)
    return result


def any_supported_emulator_running(*, system: str | None = None,
                                   process_names: Callable[[], set[str]] | None = None,
                                   environ: Mapping[str, str] | None = None) -> bool:
    return bool(running_emulators(system=system, process_names=process_names, environ=environ))


def emulator_for_path(path: Path) -> EmulatorBackend | None:
    parts = [part.casefold() for part in Path(path).parts]
    if "ryujinx" in parts or "bis" in parts and "save" in parts:
        return RYUJINX
    if "cemu" in parts or "mlc01" in parts:
        return CEMU
    return None