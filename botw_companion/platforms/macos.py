from __future__ import annotations

from pathlib import Path
from typing import Mapping


def companion_data_dir(_environ: Mapping[str, str], home: Path) -> Path:
    return home / "Library" / "Application Support" / "BOTW Companion"


def ryujinx_save_roots(_environ: Mapping[str, str], home: Path) -> list[Path]:
    return [
        home / "Library" / "Application Support" / "Ryujinx" / "bis" / "user" / "save",
        home / ".config" / "Ryujinx" / "bis" / "user" / "save",
    ]