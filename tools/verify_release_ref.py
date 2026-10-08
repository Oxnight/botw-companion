#!/usr/bin/env python3
"""Require an annotated release tag to identify the exact tested commit."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from botw_companion.versioning import CURRENT_VERSION  # noqa: E402


COMMIT_PATTERN = re.compile(r"[0-9a-fA-F]{40}")


class ReleaseRefError(RuntimeError):
    """A release ref is missing, movable, or points at another commit."""


def _git(root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReleaseRefError(f"git {' '.join(arguments)} failed") from exc
    return result.stdout.strip()


def verify_release_ref(root: Path, tag: str, expected_commit: str) -> None:
    if tag != CURRENT_VERSION.tag:
        raise ReleaseRefError(
            f"release tag {tag!r} does not match {CURRENT_VERSION.tag!r}"
        )
    if COMMIT_PATTERN.fullmatch(expected_commit) is None:
        raise ReleaseRefError("expected commit must be a full 40-character SHA")
    reference = f"refs/tags/{tag}"
    if _git(root, "cat-file", "-t", reference) != "tag":
        raise ReleaseRefError("release tag must be annotated")
    tagged_commit = _git(root, "rev-parse", f"{reference}^{{commit}}")
    head_commit = _git(root, "rev-parse", "HEAD")
    # On a tag push GitHub may expose either the peeled commit or the
    # annotated tag object as GITHUB_SHA. Resolve both forms to the commit
    # before comparing them with the checked-out source.
    try:
        workflow_commit = _git(root, "rev-parse", f"{expected_commit}^{{commit}}")
    except ReleaseRefError as exc:
        raise ReleaseRefError("workflow commit cannot be resolved") from exc
    if tagged_commit.casefold() != workflow_commit.casefold():
        raise ReleaseRefError("release tag does not point at the workflow commit")
    if head_commit.casefold() != workflow_commit.casefold():
        raise ReleaseRefError("checked-out source does not match the workflow commit")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        verify_release_ref(args.root.resolve(), args.tag, args.commit)
    except ReleaseRefError as exc:
        parser.error(str(exc))
    print(f"Verified annotated release tag {args.tag} at {args.commit}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
