#!/usr/bin/env python3
"""Verify a GitHub draft or published release against local build outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from botw_companion.versioning import CURRENT_VERSION  # noqa: E402


DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
ALLOWED_CONTENT_TYPES = {
    "application/octet-stream",
    "application/x-apple-diskimage",
    "application/x-msdownload",
}


class ReleaseAssetError(RuntimeError):
    """Published release metadata does not match the validated packages."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def verify_release_assets(
    payload: dict,
    assets_directory: Path,
    repository: str,
    *,
    published: bool,
) -> None:
    expected_names = {CURRENT_VERSION.installer_name, CURRENT_VERSION.dmg_name}
    if payload.get("tag_name") != CURRENT_VERSION.tag:
        raise ReleaseAssetError("release tag does not match the packaged version")
    if payload.get("name") != CURRENT_VERSION.title:
        raise ReleaseAssetError("release title does not match the packaged version")
    if payload.get("prerelease") is not CURRENT_VERSION.is_prerelease:
        raise ReleaseAssetError("release channel does not match the version suffix")
    expected_draft = not published
    if payload.get("draft") is not expected_draft:
        state = "published" if published else "draft"
        raise ReleaseAssetError(f"release is not in the expected {state} state")
    assets = payload.get("assets")
    if not isinstance(assets, list) or len(assets) != 2:
        raise ReleaseAssetError("release must contain exactly two uploaded assets")
    by_name = {
        asset.get("name"): asset for asset in assets if isinstance(asset, dict)
    }
    if set(by_name) != expected_names:
        raise ReleaseAssetError("release asset names are incomplete or unexpected")
    for name in sorted(expected_names):
        path = assets_directory / name
        asset = by_name[name]
        if path.is_symlink() or not path.is_file():
            raise ReleaseAssetError(f"local asset is missing or unsafe: {name}")
        if asset.get("state") != "uploaded":
            raise ReleaseAssetError(f"GitHub has not completed the upload: {name}")
        if asset.get("size") != path.stat().st_size:
            raise ReleaseAssetError(f"uploaded size differs from local asset: {name}")
        digest = asset.get("digest")
        if not isinstance(digest, str) or DIGEST_PATTERN.fullmatch(digest.casefold()) is None:
            raise ReleaseAssetError(f"GitHub digest is missing or invalid: {name}")
        if digest.casefold() != _sha256(path):
            raise ReleaseAssetError(f"GitHub digest differs from local asset: {name}")
        if asset.get("content_type") not in ALLOWED_CONTENT_TYPES:
            raise ReleaseAssetError(f"unexpected asset media type: {name}")
        expected_url = (
            f"https://github.com/{repository}/releases/download/"
            f"{CURRENT_VERSION.tag}/{name}"
        )
        if asset.get("browser_download_url") != expected_url:
            raise ReleaseAssetError(f"unexpected asset URL: {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--published", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.metadata.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        parser.error(f"unreadable GitHub release metadata: {exc}")
    if not isinstance(payload, dict):
        parser.error("GitHub release metadata must be an object")
    try:
        verify_release_assets(
            payload,
            args.assets.resolve(),
            args.repository,
            published=args.published,
        )
    except ReleaseAssetError as exc:
        parser.error(str(exc))
    print("Verified the exact Windows and macOS release assets and GitHub digests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
