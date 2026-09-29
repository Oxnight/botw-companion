"""Assisted Apple Silicon upgrades executed outside the application bundle."""

from __future__ import annotations

import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import time
import uuid

from .platforms import companion_data_dir
from .update_downloads import UpdateInstallCandidate
from .versioning import ReleaseVersion


INSTALL_STATE_NAME = "installation-macos.plist"
RELAY_SCRIPT_NAME = "macos_update_relay.sh"
CHUNK_BYTES = 256 * 1024
DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")


class MacOSUpdateError(RuntimeError):
    """A safe, user-facing assisted-upgrade failure."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _application_bundle(executable: Path) -> Path | None:
    for parent in (executable, *executable.parents):
        if parent.suffix.casefold() == ".app":
            return parent
    return None


def _safe_state(path: Path) -> dict:
    try:
        with path.open("rb") as stream:
            value = plistlib.load(stream)
    except (OSError, plistlib.InvalidFileException, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _inside_root(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((str(path.resolve()), str(root.resolve()))) == str(root.resolve())
    except (OSError, ValueError):
        return False


def _valid_candidate_metadata(candidate: UpdateInstallCandidate) -> bool:
    try:
        metadata = json.loads(candidate.metadata.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return bool(
        isinstance(metadata, dict)
        and metadata.get("ready") is True
        and metadata.get("version") == candidate.version
        and metadata.get("filename") == candidate.installer.name
        and metadata.get("size") == candidate.size
        and metadata.get("digest") == f"sha256:{candidate.digest}"
    )


class MacOSUpdateInstaller:
    """Prepare a detached system-shell relay that replaces the stopped app."""

    def __init__(
        self,
        *,
        data_root: str | Path | None = None,
        application: str | Path | None = None,
        helper: str | Path | None = None,
        system: str | None = None,
        machine: str | None = None,
        frozen: bool | None = None,
        owner_uid: int | None = None,
        owner_gid: int | None = None,
        popen=subprocess.Popen,
    ) -> None:
        self.root = Path(data_root) if data_root is not None else companion_data_dir() / "updates"
        self.executable = Path(application or sys.executable).resolve()
        self.application = _application_bundle(self.executable)
        packaged_helper = files("botw_companion").joinpath(RELAY_SCRIPT_NAME)
        self.helper = Path(helper).resolve() if helper is not None else Path(str(packaged_helper)).resolve()
        self.system = system or platform.system()
        self.machine = (machine or platform.machine()).casefold()
        self.frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
        self.owner_uid = owner_uid
        self.owner_gid = owner_gid
        self.popen = popen
        self._process = None

    @property
    def state_path(self) -> Path:
        return self.root / INSTALL_STATE_NAME

    def supported(self) -> bool:
        return bool(
            self.system == "Darwin"
            and self.machine == "arm64"
            and self.frozen
            and self.application is not None
            and self.application.name == "BOTW Companion.app"
            and self.application.is_dir()
            and self.executable.is_file()
            and self.helper.is_file()
        )

    def status(self) -> dict:
        state = _safe_state(self.state_path)
        allowed = {
            "status", "version", "message", "release_url", "can_retry",
            "log_available", "log_path", "updated_at", "rollback_performed",
        }
        public = {key: value for key, value in state.items() if key in allowed}
        public.setdefault("status", "inactive")
        public["supported"] = self.supported()
        return public

    def _write_failed_state(self, candidate: UpdateInstallCandidate, message: str,
                            log_path: Path) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        with temporary.open("wb") as stream:
            plistlib.dump({
                "schema_version": 1,
                "status": "failed",
                "version": candidate.version,
                "message": message,
                "release_url": candidate.release_url,
                "can_retry": True,
                "log_available": log_path.is_file(),
                "log_path": str(log_path),
                "rollback_performed": False,
                "updated_at": int(time.time()),
            }, stream)
        os.replace(temporary, self.state_path)

    def start(self, candidate: UpdateInstallCandidate, *, parent_pid: int, port: int) -> dict:
        if not self.supported() or self.application is None:
            raise MacOSUpdateError(
                "L’installation assistée est disponible uniquement dans l’application macOS Apple Silicon."
            )
        if self._process is not None and self._process.poll() is None:
            raise MacOSUpdateError("Une installation de mise à jour est déjà en cours")
        getuid = getattr(os, "getuid", None)
        getgid = getattr(os, "getgid", None)
        owner_uid = self.owner_uid if self.owner_uid is not None else (
            getuid() if getuid is not None else None
        )
        owner_gid = self.owner_gid if self.owner_gid is not None else (
            getgid() if getgid is not None else None
        )
        if owner_uid is None or owner_gid is None:
            raise MacOSUpdateError("L’identité du compte macOS ne peut pas être vérifiée")
        parsed = ReleaseVersion.parse(candidate.version)
        if candidate.installer.name != parsed.dmg_name:
            raise MacOSUpdateError("Nom d’image disque incohérent")
        if (
            candidate.release_url != (
                f"https://github.com/Oxnight/botw-companion/releases/tag/{parsed.tag}"
            )
            or not _inside_root(candidate.installer, self.root)
            or not _inside_root(candidate.metadata, self.root)
            or not DIGEST_PATTERN.fullmatch(candidate.digest)
            or not candidate.installer.is_file()
            or candidate.installer.stat().st_size != candidate.size
            or sha256_file(candidate.installer) != candidate.digest
            or not _valid_candidate_metadata(candidate)
        ):
            raise MacOSUpdateError("La vérification de sécurité avant installation a échoué")

        relay_dir = self.root / "relay-macos" / f"{candidate.version}-{uuid.uuid4().hex}"
        relay = relay_dir / RELAY_SCRIPT_NAME
        log_path = self.root / "logs" / f"installation-macos-{candidate.version}.log"
        try:
            relay_dir.mkdir(parents=True, exist_ok=False)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.helper, relay)
            relay.chmod(0o700)
        except OSError as exc:
            self._write_failed_state(
                candidate,
                "Le relais macOS ne peut pas être préparé sur le disque.",
                log_path,
            )
            raise MacOSUpdateError("Le relais macOS ne peut pas être préparé") from exc

        scheduled = {
            "schema_version": 1,
            "status": "scheduled",
            "version": candidate.version,
            "message": "Arrêt sécurisé de BOTW Companion avant la mise à jour…",
            "release_url": candidate.release_url,
            "can_retry": False,
            "log_available": False,
            "log_path": str(log_path),
            "rollback_performed": False,
            "updated_at": int(time.time()),
        }
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        with temporary.open("wb") as stream:
            plistlib.dump(scheduled, stream)
        os.replace(temporary, self.state_path)

        command = [
            "/bin/bash", str(relay),
            "--root", str(self.root.resolve()),
            "--dmg", str(candidate.installer.resolve()),
            "--metadata", str(candidate.metadata.resolve()),
            "--version", candidate.version,
            "--runtime-version", parsed.pep440,
            "--short-version", parsed.macos_short,
            "--bundle-version", parsed.macos_bundle,
            "--digest", candidate.digest,
            "--size", str(candidate.size),
            "--parent-pid", str(parent_pid),
            "--application", str(self.application.resolve()),
            "--port", str(port),
            "--log", str(log_path.resolve()),
            "--release-url", candidate.release_url,
            "--owner-uid", str(owner_uid),
            "--owner-gid", str(owner_gid),
        ]
        try:
            self._process = self.popen(
                command,
                cwd=relay_dir,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
                env={
                    "HOME": os.environ.get("HOME", ""),
                    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                    "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
                },
            )
        except OSError as exc:
            self._write_failed_state(
                candidate,
                "Le relais macOS n’a pas pu démarrer.",
                log_path,
            )
            raise MacOSUpdateError("Le relais macOS n’a pas pu démarrer") from exc
        return self.status()
