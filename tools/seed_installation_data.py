#!/usr/bin/env python3
"""Seed synthetic compatibility data for native installer validation only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/installation_user_data.json"


def seed(destination: Path) -> None:
    payloads = json.loads(FIXTURE.read_text(encoding="utf-8"))
    expected = {"manual_tracking.json", "route_sessions.json", "preferences.json", "export-reference.json"}
    if set(payloads) != expected:
        raise ValueError("The installation fixture must contain exactly the expected data files")
    destination.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        (destination / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    seed(parser.parse_args().destination)


if __name__ == "__main__":
    main()
