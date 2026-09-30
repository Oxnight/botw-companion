#!/usr/bin/env python3
"""Verify a GitHub draft or published release against local build outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from botw_companion.versioning import CURRENT_VERSION  # noqa: E402


DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
DRAFT_DOWNLOAD_TOKEN_PATTERN = re.compile(r"untagged-[0-9a-f]{20,64}")
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


def _positive_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validate_https_url(value: object, host: str, path: str) -> None:
    if not isinstance(value, str):
        raise ReleaseAssetError("GitHub metadata contains a missing URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != host
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != path
        or parsed.query
        or parsed.fragment
    ):
        raise ReleaseAssetError("GitHub metadata contains an unexpected URL")


def _draft_download_token(value: object, repository: str, name: str) -> str:
    if not isinstance(value, str):
        raise ReleaseAssetError(f"missing draft asset URL: {name}")
    parsed = urlsplit(value)
    prefix = f"/{repository}/releases/download/"
    suffix = f"/{name}"
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.path.startswith(prefix)
        or not parsed.path.endswith(suffix)
        or parsed.query
        or parsed.fragment
    ):
        raise ReleaseAssetError(f"unexpected draft asset URL: {name}")
    token = parsed.path[len(prefix):-len(suffix)]
    if DRAFT_DOWNLOAD_TOKEN_PATTERN.fullmatch(token) is None:
        raise ReleaseAssetError(f"unexpected draft asset URL: {name}")
    return token


def verify_release_assets(
    payload: dict,
    assets_directory: Path,
    repository: str,
    *,
    published: bool,
) -> None:
    if REPOSITORY_PATTERN.fullmatch(repository) is None:
        raise ReleaseAssetError("invalid GitHub repository name")
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
    release_id = payload.get("id")
    if not _positive_integer(release_id):
        raise ReleaseAssetError("release database ID is missing or invalid")
    api_prefix = f"/repos/{repository}/releases"
    _validate_https_url(
        payload.get("url"), "api.github.com", f"{api_prefix}/{release_id}"
    )
    _validate_https_url(
        payload.get("assets_url"),
        "api.github.com",
        f"{api_prefix}/{release_id}/assets",
    )
    assets = payload.get("assets")
    if not isinstance(assets, list) or len(assets) != 2:
        raise ReleaseAssetError("release must contain exactly two uploaded assets")
    by_name = {
        asset.get("name"): asset for asset in assets if isinstance(asset, dict)
    }
    if set(by_name) != expected_names:
        raise ReleaseAssetError("release asset names are incomplete or unexpected")
    asset_ids: set[int] = set()
    draft_token: str | None = None
    for name in sorted(expected_names):
        path = assets_directory / name
        asset = by_name[name]
        if path.is_symlink() or not path.is_file():
            raise ReleaseAssetError(f"local asset is missing or unsafe: {name}")
        if asset.get("state") != "uploaded":
            raise ReleaseAssetError(f"GitHub has not completed the upload: {name}")
        asset_id = asset.get("id")
        if not _positive_integer(asset_id) or asset_id in asset_ids:
            raise ReleaseAssetError(f"GitHub asset ID is missing or duplicated: {name}")
        asset_ids.add(asset_id)
        _validate_https_url(
            asset.get("url"),
            "api.github.com",
            f"{api_prefix}/assets/{asset_id}",
        )
        if asset.get("size") != path.stat().st_size:
            raise ReleaseAssetError(f"uploaded size differs from local asset: {name}")
        digest = asset.get("digest")
        if not isinstance(digest, str) or DIGEST_PATTERN.fullmatch(digest.casefold()) is None:
            raise ReleaseAssetError(f"GitHub digest is missing or invalid: {name}")
        if digest.casefold() != _sha256(path):
            raise ReleaseAssetError(f"GitHub digest differs from local asset: {name}")
        if asset.get("content_type") not in ALLOWED_CONTENT_TYPES:
            raise ReleaseAssetError(f"unexpected asset media type: {name}")
        if published:
            expected_url = (
                f"https://github.com/{repository}/releases/download/"
                f"{CURRENT_VERSION.tag}/{name}"
            )
            if asset.get("browser_download_url") != expected_url:
                raise ReleaseAssetError(f"unexpected published asset URL: {name}")
        else:
            token = _draft_download_token(
                asset.get("browser_download_url"), repository, name
            )
            if draft_token is None:
                draft_token = token
            elif token != draft_token:
                raise ReleaseAssetError("draft assets do not share one release URL")


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
