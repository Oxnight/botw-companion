from __future__ import annotations

from pathlib import Path
from typing import Mapping


def companion_data_dir(environ: Mapping[str, str], home: Path) -> Path:
    return Path(environ.get("XDG_DATA_HOME", home / ".local" / "share")) / "botw-companion"


def ryujinx_save_roots(environ: Mapping[str, str], home: Path) -> list[Path]:
    config = Path(environ.get("XDG_CONFIG_HOME", home / ".config"))
    return [config / "Ryujinx" / "bis" / "user" / "save"]