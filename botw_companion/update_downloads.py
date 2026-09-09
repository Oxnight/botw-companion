"""Secure, resumable downloads for validated BOTW Companion releases."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import threading
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .persistence import atomic_write_json
from .platforms import companion_data_dir
from .updates import MAX_ASSET_BYTES, UpdateChecker
from .versioning import ReleaseVersion


CHUNK_BYTES = 256 * 1024
DISK_RESERVE_BYTES = 32 * 1024 * 1024
CONNECT_TIMEOUT_SECONDS = 15.0
MAX_ATTEMPTS = 3
META_SCHEMA_VERSION = 1
ACTIVE_STATES = {"checking", "downloading", "verifying"}
DIGEST_PATTERN = re.compile(r"sha256:([0-9a-f]{64})")
CONTENT_RANGE_PATTERN = re.compile(r"bytes (\d+)-(\d+)/(\d+)")
ALLOWED_REDIRECT_HOSTS = {
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}


class UpdateDownloadError(RuntimeError):
    """A safe, user-facing update download failure."""


class DownloadCancelled(UpdateDownloadError):
    """The user cancelled the active transfer."""


class DownloadInterrupted(UpdateDownloadError):
    """A retryable network interruption that preserves partial bytes."""


def _trusted_download_url(value: object, *, initial: bool = False) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_REDIRECT_HOSTS
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        return False
    if initial:
        return (
            parsed.hostname == "github.com"
            and parsed.path.startswith("/Oxnight/botw-companion/releases/download/")
            and not parsed.query
        )
    return True


class SafeDownloadRedirectHandler(HTTPRedirectHandler):
    """Allow only the HTTPS hosts used by GitHub release assets."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _trusted_download_url(newurl):
            raise UpdateDownloadError("Redirection de téléchargement non reconnue")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _default_opener(request: Request, *, timeout: float):
    return build_opener(SafeDownloadRedirectHandler()).open(request, timeout=timeout)


def _header(response, name: str) -> str | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    value = headers.get(name)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _status(response) -> int:
    value = getattr(response, "status", None)
    if value is None:
        value = response.getcode()
    return int(value)


def _final_url(response, fallback: str) -> str:
    getter = getattr(response, "geturl", None)
    return getter() if callable(getter) else fallback


@dataclass(frozen=True)
class DownloadTarget:
    version: str
    filename: str
    url: str
    size: int
    digest: str
    release_url: str

    @classmethod
    def from_check(cls, payload: object) -> "DownloadTarget":
        if isinstance(payload, dict) and payload.get("status") == "unavailable":
            raise DownloadInterrupted(
                "Connexion indisponible. Réessaie plus tard ; le Companion reste utilisable hors ligne."
            )
        if not isinstance(payload, dict) or payload.get("update_available") is not True:
            raise UpdateDownloadError("Aucune mise à jour téléchargeable")
        version = payload.get("latest_version")
        filename = payload.get("filename")
        url = payload.get("download_url")
        size = payload.get("size")
        digest_value = payload.get("digest")
        release_url = payload.get("release_url")
        digest_match = DIGEST_PATTERN.fullmatch(digest_value) if isinstance(digest_value, str) else None
        try:
            parsed_version = ReleaseVersion.parse(version) if isinstance(version, str) else None
        except ValueError:
            parsed_version = None
        expected_names = (
            {parsed_version.installer_name, parsed_version.dmg_name}
            if parsed_version is not None else set()
        )
        expected_release_url = (
            f"https://github.com/Oxnight/botw-companion/releases/tag/{parsed_version.tag}"
            if parsed_version is not None else None
        )
        expected_download_url = (
            f"https://github.com/Oxnight/botw-companion/releases/download/{parsed_version.tag}/{filename}"
            if parsed_version is not None and isinstance(filename, str) else None
        )
        if (
            parsed_version is None
            or not isinstance(filename, str)
            or filename != Path(filename).name
            or filename in {"", ".", ".."}
            or filename not in expected_names
            or not _trusted_download_url(url, initial=True)
            or url != expected_download_url
            or not isinstance(size, int)
            or isinstance(size, bool)
            or not 0 < size <= MAX_ASSET_BYTES
            or digest_match is None
            or not isinstance(release_url, str)
            or release_url != expected_release_url
        ):
            raise UpdateDownloadError("Métadonnées de mise à jour invalides")
        return cls(
            version=version,
            filename=filename,
            url=url,
            size=size,
            digest=digest_match.group(1),
            release_url=release_url,
        )

    def metadata(self, *, etag: str | None = None, last_modified: str | None = None) -> dict:
        return {
            "schema_version": META_SCHEMA_VERSION,
            "version": self.version,
            "filename": self.filename,
            "url": self.url,
            "size": self.size,
            "digest": f"sha256:{self.digest}",
            "etag": etag,
            "last_modified": last_modified,
        }

    def matches(self, metadata: object) -> bool:
        if not isinstance(metadata, dict):
            return False
        expected = self.metadata()
        return all(metadata.get(key) == value for key, value in expected.items() if key not in {"etag", "last_modified"})


class UpdateDownloadManager:
    """Own one background transfer and expose a small serializable state."""

    def __init__(
        self,
        checker: UpdateChecker,
        *,
        data_root: str | Path | None = None,
        opener: Callable = _default_opener,
        timeout: float = CONNECT_TIMEOUT_SECONDS,
        max_attempts: int = MAX_ATTEMPTS,
        sleeper: Callable[[float], None] = time.sleep,
        random_value: Callable[[], float] = random.random,
        disk_usage: Callable = shutil.disk_usage,
    ) -> None:
        self.checker = checker
        self.root = Path(data_root) if data_root is not None else companion_data_dir() / "updates"
        self.opener = opener
        self.timeout = timeout
        self.max_attempts = max(1, int(max_attempts))
        self.sleeper = sleeper
        self.random_value = random_value
        self.disk_usage = disk_usage
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._state = self._empty_state()

    @staticmethod
    def _empty_state() -> dict:
        return {
            "status": "inactive",
            "version": None,
            "filename": None,
            "bytes_received": 0,
            "bytes_total": 0,
            "progress": 0.0,
            "bytes_per_second": 0,
            "message": None,
            "release_url": None,
            "can_cancel": False,
            "can_retry": False,
            "ready_to_install": False,
        }

    def status(self) -> dict:
        with self._lock:
            return dict(self._state)

    def _set_state(self, status: str, **values) -> None:
        with self._lock:
            self._state.update(values)
            self._state["status"] = status
            self._state["can_cancel"] = status in ACTIVE_STATES
            self._state["can_retry"] = status in {"interrupted", "failed", "cancelled"}
            self._state["ready_to_install"] = status == "ready_to_install"

    def start(self) -> dict:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return dict(self._state)
            self._cancel.clear()
            self._state = self._empty_state()
            self._set_state("checking", message="Validation de la mise à jour…")
            self._thread = threading.Thread(
                target=self._run,
                name="botw-companion-update-download",
                daemon=True,
            )
            self._thread.start()
            return dict(self._state)

    def retry(self) -> dict:
        with self._lock:
            if self._state["status"] not in {"interrupted", "failed", "cancelled", "inactive"}:
                return dict(self._state)
        return self.start()

    def cancel(self) -> dict:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                return dict(self._state)
            self._cancel.set()
            self._state["message"] = "Annulation en cours…"
            return dict(self._state)

    def close(self, timeout: float = 2.0) -> None:
        self._cancel.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=max(0.0, timeout))

    def _run(self) -> None:
        try:
            target = DownloadTarget.from_check(self.checker.check(force=True))
            self._prepare_target(target)
            self._download_with_retries(target)
        except DownloadCancelled:
            self._set_state("cancelled", message="Téléchargement annulé. Le fragment valide est conservé.")
        except DownloadInterrupted as exc:
            self._set_state("interrupted", message=str(exc))
        except UpdateDownloadError as exc:
            self._set_state("failed", message=str(exc))
        except Exception:
            self._set_state("failed", message="Le téléchargement a échoué sans affecter le Companion.")

    def _prepare_target(self, target: DownloadTarget) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._cleanup_other_targets(target)
        part, _final, metadata_path = self._paths(target)
        metadata = self._read_metadata(metadata_path)
        if part.exists() and (not target.matches(metadata) or part.stat().st_size > target.size):
            part.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
        received = part.stat().st_size if part.exists() else 0
        self._set_state(
            "downloading",
            version=target.version,
            filename=target.filename,
            bytes_received=received,
            bytes_total=target.size,
            progress=round(received * 100 / target.size, 2),
            bytes_per_second=0,
            message="Reprise du téléchargement…" if received else "Téléchargement en cours…",
            release_url=target.release_url,
        )

    def _download_with_retries(self, target: DownloadTarget) -> None:
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            self._raise_if_cancelled()
            try:
                self._download_once(target)
                return
            except DownloadCancelled:
                raise
            except UpdateDownloadError:
                raise
            except HTTPError as exc:
                if exc.code not in {408, 429, 500, 502, 503, 504}:
                    raise UpdateDownloadError("GitHub a refusé le téléchargement de cette mise à jour") from exc
                last_error = exc
            except (URLError, TimeoutError, OSError) as exc:
                last_error = exc
            if attempt + 1 >= self.max_attempts:
                break
            self._set_state("interrupted", message="Connexion interrompue. Nouvelle tentative…")
            self.sleeper((2 ** attempt) + self.random_value())
            self._set_state("downloading", message="Reprise du téléchargement…")
        raise DownloadInterrupted(
            "Connexion interrompue. Le fragment valide est conservé ; utilise Réessayer."
        ) from last_error

    def _download_once(self, target: DownloadTarget) -> None:
        part, final, metadata_path = self._paths(target)
        metadata = self._read_metadata(metadata_path)
        if final.is_file() and target.matches(metadata) and metadata.get("ready") is True:
            if self._file_matches(final, target):
                self._set_state(
                    "ready_to_install",
                    bytes_received=target.size,
                    bytes_total=target.size,
                    progress=100.0,
                    message="Téléchargement déjà présent et vérifié.",
                )
                return
            final.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            metadata = {}
        offset = part.stat().st_size if part.exists() and target.matches(metadata) else 0
        if offset == target.size:
            self._verify_and_publish(target, part, final, metadata_path)
            return
        self._require_disk_space(target.size - offset)
        headers = {
            "Accept": "application/octet-stream",
            "User-Agent": "BOTW-Companion-Updater",
            "Accept-Encoding": "identity",
        }
        validator = None
        if offset:
            headers["Range"] = f"bytes={offset}-"
            validator = metadata.get("etag") or metadata.get("last_modified")
            if isinstance(validator, str) and validator:
                headers["If-Range"] = validator
        request = Request(target.url, headers=headers)
        try:
            response_context = self.opener(request, timeout=self.timeout)
        except HTTPError as exc:
            if exc.code == 416 and offset:
                part.unlink(missing_ok=True)
                metadata_path.unlink(missing_ok=True)
                return self._download_once(target)
            raise
        with response_context as response:
            status = _status(response)
            final_url = _final_url(response, target.url)
            if not _trusted_download_url(final_url):
                raise UpdateDownloadError("Destination de téléchargement non reconnue")
            append = offset > 0 and status == 206
            if status not in {200, 206}:
                raise UpdateDownloadError("Réponse de téléchargement inattendue")
            media_type = (_header(response, "Content-Type") or "application/octet-stream").split(";", 1)[0].strip().casefold()
            if media_type not in {
                "application/octet-stream",
                "application/x-msdownload",
                "application/x-apple-diskimage",
            }:
                raise UpdateDownloadError("Le serveur n’a pas renvoyé un paquet d’installation")
            if status == 206:
                content_range = _header(response, "Content-Range")
                match = CONTENT_RANGE_PATTERN.fullmatch(content_range or "")
                if match is None or int(match.group(1)) != offset or int(match.group(3)) != target.size:
                    raise UpdateDownloadError("Réponse de reprise incohérente")
            elif offset:
                append = False
                offset = 0
            content_length = _header(response, "Content-Length")
            expected_body = target.size - offset
            if content_length is not None:
                try:
                    declared = int(content_length)
                except ValueError as exc:
                    raise UpdateDownloadError("Taille de téléchargement invalide") from exc
                if declared != expected_body:
                    raise UpdateDownloadError("Taille de téléchargement inattendue")
            etag = _header(response, "ETag")
            last_modified = _header(response, "Last-Modified")
            atomic_write_json(metadata_path, target.metadata(etag=etag, last_modified=last_modified))
            self._stream(response, target, part, append=append, offset=offset)
        self._verify_and_publish(target, part, final, metadata_path)

    def _stream(self, response, target: DownloadTarget, part: Path, *, append: bool, offset: int) -> None:
        mode = "ab" if append else "wb"
        received = offset
        started = time.monotonic()
        with part.open(mode) as output:
            try:
                os.chmod(part, 0o600)
            except OSError:
                pass
            while True:
                self._raise_if_cancelled()
                chunk = response.read(CHUNK_BYTES)
                if not chunk:
                    break
                received += len(chunk)
                if received > target.size:
                    raise UpdateDownloadError("Le téléchargement dépasse la taille annoncée")
                output.write(chunk)
                elapsed = max(time.monotonic() - started, 0.001)
                self._require_disk_space(target.size - received)
                self._set_state(
                    "downloading",
                    bytes_received=received,
                    bytes_total=target.size,
                    progress=round(received * 100 / target.size, 2),
                    bytes_per_second=max(0, int((received - offset) / elapsed)),
                    message="Téléchargement en cours…",
                )
            output.flush()
            os.fsync(output.fileno())
        if received != target.size:
            raise OSError("truncated download")

    def _verify_and_publish(self, target: DownloadTarget, part: Path, final: Path, metadata_path: Path) -> None:
        self._raise_if_cancelled()
        self._set_state("verifying", message="Vérification du téléchargement…")
        if not part.is_file() or part.stat().st_size != target.size:
            raise UpdateDownloadError("Le paquet téléchargé est incomplet")
        if not self._file_matches(part, target, cancellable=True):
            part.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            raise UpdateDownloadError("La vérification de sécurité du paquet a échoué")
        os.replace(part, final)
        atomic_write_json(metadata_path, {**target.metadata(), "ready": True})
        self._set_state(
            "ready_to_install",
            bytes_received=target.size,
            bytes_total=target.size,
            progress=100.0,
            bytes_per_second=0,
            message="Téléchargement terminé et vérifié.",
        )

    def _file_matches(self, path: Path, target: DownloadTarget, *, cancellable: bool = False) -> bool:
        if not path.is_file() or path.stat().st_size != target.size:
            return False
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(CHUNK_BYTES):
                if cancellable:
                    self._raise_if_cancelled()
                digest.update(chunk)
        return digest.hexdigest() == target.digest

    def _require_disk_space(self, remaining: int) -> None:
        try:
            free = self.disk_usage(self.root).free
        except OSError as exc:
            raise UpdateDownloadError("Impossible de vérifier l’espace disque disponible") from exc
        if free < max(0, remaining) + DISK_RESERVE_BYTES:
            raise UpdateDownloadError("Espace disque insuffisant pour télécharger la mise à jour")

    def _cleanup_other_targets(self, target: DownloadTarget) -> None:
        allowed = {
            target.filename,
            f"{target.filename}.part",
            f"{target.filename}.metadata.json",
        }
        for path in self.root.iterdir():
            if path.is_file() and path.name not in allowed:
                path.unlink(missing_ok=True)

    def _paths(self, target: DownloadTarget) -> tuple[Path, Path, Path]:
        final = self.root / target.filename
        return final.with_name(f"{final.name}.part"), final, final.with_name(f"{final.name}.metadata.json")

    @staticmethod
    def _read_metadata(path: Path) -> dict:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _raise_if_cancelled(self) -> None:
        if self._cancel.is_set():
            raise DownloadCancelled("Téléchargement annulé")
