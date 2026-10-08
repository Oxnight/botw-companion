#!/usr/bin/env python3
"""Resolve exactly one GitHub Release from paginated REST metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


class ReleaseLookupError(ValueError):
    """Raised when release metadata is malformed or ambiguous."""


def _flatten(payload: object) -> list[dict]:
    if not isinstance(payload, list):
        raise ReleaseLookupError("release metadata must be a JSON array")
    releases: list[dict] = []
    for item in payload:
        if isinstance(item, list):
            pages = item
        else:
            pages = [item]
        for release in pages:
            if not isinstance(release, dict):
                raise ReleaseLookupError("release metadata contains a non-object entry")
            releases.append(release)
    return releases


def find_release_id(payload: object, tag: str, state: str = "any") -> int:
    matches = []
    for release in _flatten(payload):
        if release.get("tag_name") != tag:
            continue
        draft = release.get("draft")
        if not isinstance(draft, bool):
            raise ReleaseLookupError("matching release has no boolean draft state")
        if state == "draft" and not draft:
            continue
        if state == "published" and draft:
            continue
        identifier = release.get("id")
        if not isinstance(identifier, int) or identifier <= 0:
            raise ReleaseLookupError("matching release has no valid database id")
        matches.append(identifier)
    if not matches:
        raise ReleaseLookupError(f"release {tag!r} was not found in state {state!r}")
    if len(matches) != 1:
        raise ReleaseLookupError(f"release {tag!r} is ambiguous")
    return matches[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--state", choices=("any", "draft", "published"), default="any")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.metadata.read_text(encoding="utf-8"))
        print(find_release_id(payload, args.tag, args.state))
    except (OSError, json.JSONDecodeError, ReleaseLookupError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
