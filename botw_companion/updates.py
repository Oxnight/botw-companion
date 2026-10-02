"""Optional checks for new versions published on GitHub."""

from __future__ import annotations

import json
from http.client import HTTPException
import re
from threading import RLock
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request

from .platforms import platform_id
from .secure_transport import CertificateBundleError, network_failure_reason, secure_urlopen
from .versioning import CURRENT_VERSION, ReleaseVersion


REPOSITORY = "Oxnight/botw-companion"
RELEASES_API = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=10"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases"
MAX_RESPONSE_BYTES = 1_000_000
MAX_ASSET_BYTES = 1_073_741_824
DEFAULT_TIMEOUT_SECONDS = 15.0
MAX_CHECK_ATTEMPTS = 2
CHECK_RETRY_DELAY_SECONDS = 0.75
RETRYABLE_HTTP_STATUSES = {408, 500, 502, 503, 504}
SUCCESS_CACHE_SECONDS = 15 * 60
FAILURE_CACHE_SECONDS = 60


class UpdateCheckError(RuntimeError):
    """Unusable remote response that does not affect offline operation."""

    def __init__(self, message: str, *, reason: str = "invalid_response",
                 retryable: bool = False) -> None:
        super().__init__(message)
        self.reason = reason
        self.retryable = retryable


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
        opener: Callable = secure_urlopen,
        monotonic: Callable[[], float] = time.monotonic,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_attempts: int = MAX_CHECK_ATTEMPTS,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.current = current
        self.system = system
        self.opener = opener
        self.monotonic = monotonic
        self.timeout = timeout
        self.max_attempts = max(1, int(max_attempts))
        self.sleeper = sleeper
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

    @staticmethod
    def _rate_limited(error: HTTPError) -> bool:
        headers = getattr(error, "headers", None)
        remaining = headers.get("X-RateLimit-Remaining") if headers is not None else None
        retry_after = headers.get("Retry-After") if headers is not None else None
        return error.code == 429 or (
            error.code == 403 and (remaining == "0" or retry_after is not None)
        )

    @staticmethod
    def _network_error(exc: BaseException) -> UpdateCheckError:
        reason = network_failure_reason(exc)
        labels = {
            "timeout": "GitHub met trop de temps à répondre",
            "tls": "La connexion sécurisée à GitHub n'a pas pu être vérifiée",
            "dns": "L'adresse de GitHub n'a pas pu être résolue",
            "network": "GitHub est momentanément inaccessible",
        }
        return UpdateCheckError(
            labels[reason],
            reason=reason,
            retryable=True,
        )

    def _request_releases_once(self) -> list[dict]:
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
                    raise UpdateCheckError(
                        "Réponse GitHub inattendue",
                        reason="remote_error",
                        retryable=status in RETRYABLE_HTTP_STATUSES,
                    )
                final_url = (
                    response.geturl()
                    if callable(getattr(response, "geturl", None))
                    else RELEASES_API
                )
                if final_url != RELEASES_API:
                    raise UpdateCheckError("Redirection GitHub non reconnue")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            if self._rate_limited(exc):
                raise UpdateCheckError(
                    "GitHub limite temporairement les vérifications",
                    reason="rate_limited",
                ) from exc
            raise UpdateCheckError(
                "Réponse GitHub momentanément indisponible",
                reason="remote_error",
                retryable=exc.code in RETRYABLE_HTTP_STATUSES,
            ) from exc
        except (URLError, TimeoutError, OSError, HTTPException, CertificateBundleError) as exc:
            raise self._network_error(exc) from exc
        if len(raw) > MAX_RESPONSE_BYTES:
            raise UpdateCheckError("Réponse GitHub trop volumineuse")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UpdateCheckError("Réponse GitHub invalide") from exc
        if not isinstance(payload, list):
            raise UpdateCheckError("Liste des versions GitHub invalide")
        return [item for item in payload if isinstance(item, dict)]

    def _request_releases(self) -> list[dict]:
        last_error: UpdateCheckError | None = None
        for attempt in range(self.max_attempts):
            try:
                return self._request_releases_once()
            except UpdateCheckError as exc:
                last_error = exc
                if not exc.retryable or attempt + 1 >= self.max_attempts:
                    raise
                self.sleeper(CHECK_RETRY_DELAY_SECONDS * (2 ** attempt))
        assert last_error is not None
        raise last_error

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
                and not isinstance(item.get("size"), bool)
                and 0 < item["size"] <= MAX_ASSET_BYTES
            ),
            None,
        )
        if asset is None:
            raise UpdateCheckError("Paquet de mise à jour encore indisponible")
        download_url = _safe_download_url(tag, filename)
        if not _exact_https_url(asset.get("browser_download_url"), download_url):
            raise UpdateCheckError("Adresse de téléchargement GitHub non reconnue")
        digest = asset.get("digest")
        if not isinstance(digest, str) or re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest) is None:
            raise UpdateCheckError("Empreinte de mise à jour absente ou invalide")
        content_type = asset.get("content_type")
        allowed_types = {
            "application/octet-stream",
            "application/x-msdownload",
            "application/x-apple-diskimage",
        }
        if content_type not in allowed_types:
            raise UpdateCheckError("Type de paquet de mise à jour non reconnu")

        return {
            "status": "update_available",
            "update_available": True,
            "current_version": self.current.display,
            "latest_version": version.display,
            "title": version.title,
            "platform": target,
            "filename": filename,
            "download_url": download_url,
            "size": asset["size"],
            "digest": digest.casefold(),
            "content_type": content_type,
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
            except UpdateCheckError as exc:
                messages = {
                    "timeout": (
                        "GitHub met plus de temps que prévu à répondre. "
                        "Réessaie dans un instant ; BOTW Companion reste utilisable hors ligne."
                    ),
                    "rate_limited": (
                        "GitHub limite temporairement les vérifications. "
                        "Réessaie dans quelques minutes ; BOTW Companion reste utilisable hors ligne."
                    ),
                    "network": (
                        "Connexion à GitHub indisponible. "
                        "BOTW Companion reste entièrement utilisable hors ligne."
                    ),
                    "dns": (
                        "L’adresse de GitHub est introuvable. Vérifie le réseau ou le DNS ; "
                        "BOTW Companion reste utilisable hors ligne."
                    ),
                    "tls": (
                        "La connexion sécurisée à GitHub n’a pas pu être vérifiée. "
                        "BOTW Companion reste utilisable hors ligne."
                    ),
                }
                payload = {
                    "status": "unavailable",
                    "update_available": False,
                    "current_version": self.current.display,
                    "platform": platform_id(self.system),
                    "release_url": RELEASES_PAGE,
                    "reason": exc.reason,
                    "message": messages.get(
                        exc.reason,
                        "Vérification impossible pour le moment. "
                        "BOTW Companion reste entièrement utilisable hors ligne.",
                    ),
                }
            self._cached_at = now
            self._cached_payload = dict(payload)
            return payload
