"""Optional checks for new versions published on GitHub."""

from __future__ import annotations

import json
from threading import RLock
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from .platforms import platform_id
from .versioning import CURRENT_VERSION, ReleaseVersion


REPOSITORY = "Oxnight/botw-companion"
RELEASES_API = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=30"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases"
MAX_RESPONSE_BYTES = 1_000_000
DEFAULT_TIMEOUT_SECONDS = 3.0
SUCCESS_CACHE_SECONDS = 15 * 60
FAILURE_CACHE_SECONDS = 60


class UpdateCheckError(RuntimeError):
    """Unusable remote response that does not affect offline operation."""


def _safe_release_url(tag: str) -> str:
    return f"{RELEASES_PAGE}/tag/{quote(tag, safe='.-')}"


def _safe_download_url(tag: str, filename: str) -> str:
    return (
        f"https://github.com/{REPOSITORY}/releases/download/"
        f"{quote(tag, safe='.-')}/{quote(filename, safe='._-')}"
    )


def _exact_https_url(candidate: object, expected: str) -> bool:
    if not isinstance(candidate, str) or candidate != expected:
        return False
    parsed = urlsplit(candidate)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "github.com"
        and parsed.port is None
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )


class UpdateChecker:
    """Query GitHub with a short timeout, strict validation, and memory cache."""

    def __init__(
        self,
        *,
        current: ReleaseVersion = CURRENT_VERSION,
        system: str | None = None,
        opener: Callable = urlopen,
        monotonic: Callable[[], float] = time.monotonic,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.current = current
        self.system = system
        self.opener = opener
        self.monotonic = monotonic
        self.timeout = timeout
        self._lock = RLock()
        self._cached_at: float | None = None
        self._cached_payload: dict | None = None

    def _platform_and_filename(self, version: ReleaseVersion) -> tuple[str, str | None]:
        target = platform_id(self.system)
        if target == "windows":
            return target, version.installer_name
        if target == "macos":
            return target, version.dmg_name
        return target, None

    def _request_releases(self) -> list[dict]:
        request = Request(
            RELEASES_API,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"BOTW-Companion/{self.current.display}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                status = getattr(response, "status", None)
                if status is None:
                    status = response.getcode()
                if status != 200:
                    raise UpdateCheckError("Réponse GitHub inattendue")
                final_url = (
                    response.geturl()
                    if callable(getattr(response, "geturl", None))
                    else RELEASES_API
                )
                if final_url != RELEASES_API:
                    raise UpdateCheckError("Redirection GitHub non reconnue")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise UpdateCheckError("GitHub est momentanément inaccessible") from exc
        if len(raw) > MAX_RESPONSE_BYTES:
            raise UpdateCheckError("Réponse GitHub trop volumineuse")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UpdateCheckError("Réponse GitHub invalide") from exc
        if not isinstance(payload, list):
            raise UpdateCheckError("Liste des versions GitHub invalide")
        return [item for item in payload if isinstance(item, dict)]

    def _candidate(self, releases: list[dict]) -> tuple[ReleaseVersion, dict] | None:
        candidates: list[tuple[ReleaseVersion, dict]] = []
        for release in releases:
            if release.get("draft") is not False:
                continue
            if not self.current.is_prerelease and release.get("prerelease") is not False:
                continue
            tag = release.get("tag_name")
            if not isinstance(tag, str) or not tag.startswith("v"):
                continue
            try:
                version = ReleaseVersion.parse(tag[1:])
            except ValueError:
                continue
            if bool(release.get("prerelease")) != version.is_prerelease:
                continue
            if version.precedence > self.current.precedence:
                candidates.append((version, release))
        return max(candidates, key=lambda item: item[0].precedence, default=None)

    def _fresh_payload(self) -> dict:
        target = platform_id(self.system)
        if target not in {"windows", "macos"}:
            return {
                "status": "unsupported",
                "update_available": False,
                "current_version": self.current.display,
                "platform": target,
                "release_url": RELEASES_PAGE,
            }

        candidate = self._candidate(self._request_releases())
        if candidate is None:
            return {
                "status": "up_to_date",
                "update_available": False,
                "current_version": self.current.display,
                "platform": target,
                "release_url": RELEASES_PAGE,
            }

        version, release = candidate
        tag = version.tag
        release_url = _safe_release_url(tag)
        if not _exact_https_url(release.get("html_url"), release_url):
            raise UpdateCheckError("Adresse de release GitHub non reconnue")

        _target, filename = self._platform_and_filename(version)
        assets = release.get("assets")
        if not filename or not isinstance(assets, list):
            raise UpdateCheckError("Paquet de mise à jour absent")
        asset = next(
            (
                item for item in assets
                if isinstance(item, dict)
                and item.get("name") == filename
                and item.get("state") == "uploaded"
                and isinstance(item.get("size"), int)
                and item["size"] > 0
            ),
            None,
        )
        if asset is None:
            raise UpdateCheckError("Paquet de mise à jour encore indisponible")
        download_url = _safe_download_url(tag, filename)
        if not _exact_https_url(asset.get("browser_download_url"), download_url):
            raise UpdateCheckError("Adresse de téléchargement GitHub non reconnue")

        return {
            "status": "update_available",
            "update_available": True,
            "current_version": self.current.display,
            "latest_version": version.display,
            "title": version.title,
            "platform": target,
            "filename": filename,
            "download_url": download_url,
            "release_url": release_url,
            "prerelease": version.is_prerelease,
        }

    def check(self, *, force: bool = False) -> dict:
        """Always return usable state; network failures remain silent."""
        with self._lock:
            now = self.monotonic()
            if not force and self._cached_payload is not None and self._cached_at is not None:
                ttl = (
                    FAILURE_CACHE_SECONDS
                    if self._cached_payload.get("status") == "unavailable"
                    else SUCCESS_CACHE_SECONDS
                )
                if now - self._cached_at < ttl:
                    return dict(self._cached_payload)
            try:
                payload = self._fresh_payload()
            except UpdateCheckError:
                payload = {
                    "status": "unavailable",
                    "update_available": False,
                    "current_version": self.current.display,
                    "platform": platform_id(self.system),
                    "release_url": RELEASES_PAGE,
                    "message": "Vérification impossible pour le moment. BOTW Companion reste entièrement utilisable hors ligne.",
                }
            self._cached_at = now
            self._cached_payload = dict(payload)
            return payload
