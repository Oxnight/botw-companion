#!/usr/bin/env python3
"""Génère la ressource de version Windows utilisée par PyInstaller."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from botw_companion.versioning import CURRENT_VERSION  # noqa: E402


def render() -> str:
    version = CURRENT_VERSION
    parts = tuple(int(part) for part in version.numeric.split("."))
    return f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={parts},
    prodvers={parts},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040C04B0',
        [StringStruct(u'CompanyName', u'BOTW Companion contributors'),
         StringStruct(u'FileDescription', u'BOTW Companion'),
         StringStruct(u'FileVersion', u'{version.display}'),
         StringStruct(u'InternalName', u'BOTW Companion'),
         StringStruct(u'LegalCopyright', u'MIT'),
         StringStruct(u'OriginalFilename', u'BOTW Companion.exe'),
         StringStruct(u'ProductName', u'BOTW Companion'),
         StringStruct(u'ProductVersion', u'{version.display}')])
    ]),
    VarFileInfo([VarStruct(u'Translation', [1036, 1200])])
  ]
)
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
