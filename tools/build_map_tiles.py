#!/usr/bin/env python3
"""Build the offline multi-resolution BOTW map pyramid used by the browser."""

from __future__ import annotations

import argparse
import json
from math import ceil
from pathlib import Path

from PIL import Image


Image.MAX_IMAGE_PIXELS = None
TILE_SIZE = 1024
LEVELS = (("z1", 6000, 5000), ("z2", 12000, 10000), ("z3", 24000, 20000))


def build(source: Path, destination: Path, quality: int) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as loaded:
        original = loaded.convert("RGB")
    if original.size != (24000, 20000):
        raise SystemExit(f"Source attendue : 24000x20000, reçue : {original.size}")

    manifest = {"schema_version": 1, "logical_size": [1200, 1000],
                "tile_size": TILE_SIZE, "levels": []}
    for name, width, height in LEVELS:
        level_dir = destination / name
        level_dir.mkdir(exist_ok=True)
        image = (original if original.size == (width, height) else
                 original.resize((width, height), Image.Resampling.LANCZOS, reducing_gap=3.0))
        columns, rows = ceil(width / TILE_SIZE), ceil(height / TILE_SIZE)
        for row in range(rows):
            top = row * TILE_SIZE
            for column in range(columns):
                left = column * TILE_SIZE
                tile = image.crop((left, top, min(left + TILE_SIZE, width),
                                   min(top + TILE_SIZE, height)))
                tile.save(level_dir / f"{column}_{row}.webp", "WEBP",
                          quality=quality, method=4)
        manifest["levels"].append({"id": name, "width": width, "height": height,
                                   "density": width / 1200, "columns": columns,
                                   "rows": rows})
        if image is not original:
            image.close()

    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (destination / "SOURCE.txt").write_text(
        "Carte BOTW 24000x20000 utilisée par le projet open source ZeldaMods Object Map.\n"
        "Source : https://static.zeldamods.org/botw_map.png\n"
        "Projet : https://github.com/zeldamods/objmap\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--quality", type=int, default=88)
    args = parser.parse_args()
    build(args.source, args.destination, args.quality)


if __name__ == "__main__":
    main()