"""Assisted Windows upgrades executed outside the installed application tree."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from http.client import HTTPException
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from urllib.request import ProxyHandler, Request, build_opener

from .persistence import atomic_write_json
from .platforms import companion_data_dir
from .versioning import ReleaseVersion


UPDATER_EXE_NAME = "BOTW Companion Updater.exe"
INSTALL_STATE_NAME = "installation.json"
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CHUNK_BYTES = 256 * 1024


class WindowsUpdateError(RuntimeError):
    """A safe, user-facing assisted-upgrade failure."""


@dataclass(frozen=True)
class WindowsInstallCandidate:
    version: str
    installer: Path
    size: int
    digest: str
    metadata: Path
    release_url: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_state(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


class WindowsUpdateInstaller:
    """Copy and launch the small updater relay before the main app exits."""

    def __init__(
        self,
        *,
        data_root: str | Path | None = None,
        application: str | Path | None = None,
        helper: str | Path | None = None,
        system: str | None = None,
        frozen: bool | None = None,
        popen=subprocess.Popen,
    ) -> None:
        self.root = Path(data_root) if data_root is not None else companion_data_dir() / "updates"
        self.application = Path(application or sys.executable).resolve()
        self.helper = Path(helper).resolve() if helper is not None else self.application.with_name(UPDATER_EXE_NAME)
        self.system = system or platform.system()
        self.frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
        self.popen = popen
        self._process = None

    @property
    def state_path(self) -> Path:
        return self.root / INSTALL_STATE_NAME

    def supported(self) -> bool:
        return (
            self.system == "Windows"
            and self.frozen
            and self.application.name.casefold() == "botw companion.exe"
            and self.application.is_file()
            and self.application.with_name("unins000.exe").is_file()
            and self.helper.is_file()
        )

    def status(self) -> dict:
        state = _safe_state(self.state_path)
        allowed = {
            "status", "version", "message", "release_url", "can_retry",
            "log_available", "log_path", "updated_at",
        }
        public = {key: value for key, value in state.items() if key in allowed}
        public.setdefault("status", "inactive")
        public["supported"] = self.supported()
        return public

    def _cleanup_stale_relays(self) -> None:
        relay_root = self.root / "relay"
        if not relay_root.is_dir():
            return
        state = _safe_state(self.state_path)
        if state.get("status") in {"scheduled", "installing", "restarting"}:
            return
        for path in relay_root.iterdir():
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)

    def start(self, candidate: WindowsInstallCandidate, *, parent_pid: int, port: int) -> dict:
        if not self.supported():
            raise WindowsUpdateError(
                "L’installation assistée est disponible uniquement dans l’application Windows installée."
            )
        if self._process is not None and self._process.poll() is None:
            raise WindowsUpdateError("Une installation de mise à jour est déjà en cours")
        parsed = ReleaseVersion.parse(candidate.version)
        if candidate.installer.name != parsed.installer_name:
            raise WindowsUpdateError("Nom d’installateur incohérent")
        self._cleanup_stale_relays()
        relay_dir = self.root / "relay" / f"{candidate.version}-{uuid.uuid4().hex}"
        relay = relay_dir / UPDATER_EXE_NAME
        log_path = self.root / "logs" / f"installation-{candidate.version}.log"
        try:
            relay_dir.mkdir(parents=True, exist_ok=False)
            shutil.copy2(self.helper, relay)
            log_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            try:
                atomic_write_json(self.state_path, {
                    "schema_version": 1,
                    "status": "failed",
                    "version": candidate.version,
                    "message": "Le relais d’installation ne peut pas être préparé sur le disque.",
                    "release_url": candidate.release_url,
                    "can_retry": True,
                    "log_available": False,
                    "log_path": str(log_path),
                    "updated_at": int(time.time()),
                })
            except OSError:
                pass
            raise WindowsUpdateError("Le relais d’installation ne peut pas être préparé") from exc
        atomic_write_json(self.state_path, {
            "schema_version": 1,
            "status": "scheduled",
            "version": candidate.version,
            "message": "Arrêt sécurisé de BOTW Companion avant l’installation…",
            "release_url": candidate.release_url,
            "can_retry": False,
            "log_available": False,
            "log_path": str(log_path),
            "updated_at": int(time.time()),
        })
        command = [
            str(relay),
            "--root", str(self.root.resolve()),
            "--installer", str(candidate.installer.resolve()),
            "--metadata", str(candidate.metadata.resolve()),
            "--version", candidate.version,
            "--digest", candidate.digest,
            "--size", str(candidate.size),
            "--parent-pid", str(parent_pid),
            "--application", str(self.application),
            "--port", str(port),
            "--log", str(log_path.resolve()),
            "--release-url", candidate.release_url,
        ]
        try:
            self._process = self.popen(
                command,
                cwd=relay_dir,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                close_fds=True,
                env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"},
            )
        except OSError as exc:
            try:
                atomic_write_json(self.state_path, {
                    "schema_version": 1,
                    "status": "failed",
                    "version": candidate.version,
                    "message": "Le relais d’installation n’a pas pu démarrer.",
                    "release_url": candidate.release_url,
                    "can_retry": True,
                    "log_available": False,
                    "log_path": str(log_path),
                    "updated_at": int(time.time()),
                })
            except OSError:
                pass
            raise WindowsUpdateError("Le relais d’installation n’a pas pu démarrer") from exc
        return self.status()


def _inside_root(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((str(path.resolve()), str(root.resolve()))) == str(root.resolve())
    except (OSError, ValueError):
        return False


def _write_relay_state(root: Path, *, status: str, version: str, message: str,
                       release_url: str, can_retry: bool, log_available: bool,
                       log_path: Path) -> None:
    atomic_write_json(root / INSTALL_STATE_NAME, {
        "schema_version": 1,
        "status": status,
        "version": version,
        "message": message,
        "release_url": release_url,
        "can_retry": can_retry,
        "log_available": log_available,
        "log_path": str(log_path),
        "updated_at": int(time.time()),
    })


def _wait_for_parent(pid: int, timeout: float = 30.0) -> bool:
    if os.name != "nt":
        return True
    import ctypes
    from ctypes import wintypes
    synchronize = 0x00100000
    wait_object_0 = 0
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return True
    try:
        return kernel32.WaitForSingleObject(handle, int(timeout * 1000)) == wait_object_0
    finally:
        kernel32.CloseHandle(handle)


def _probe_version(port: int, expected: str) -> bool:
    try:
        with build_opener(ProxyHandler({})).open(
            Request(f"http://127.0.0.1:{port}/api/version"), timeout=0.5
        ) as response:
            data = json.loads(response.read(128 * 1024))
    except (OSError, HTTPException, ValueError, json.JSONDecodeError):
        return False
    return (
        isinstance(data, dict)
        and data.get("application") == "BOTW Companion"
        and data.get("version") == ReleaseVersion.parse(expected).pep440
    )


def _run_relay(args) -> int:
    root = Path(args.root).resolve()
    installer_source = Path(args.installer)
    metadata_source = Path(args.metadata)
    installer = installer_source.resolve()
    metadata = metadata_source.resolve()
    application = Path(args.application).resolve()
    log_path = Path(args.log).resolve()
    parsed = ReleaseVersion.parse(args.version)
    if (
        platform.system() != "Windows"
        or not _inside_root(installer, root)
        or not _inside_root(metadata, root)
        or not _inside_root(log_path, root)
        or installer.name != parsed.installer_name
        or installer_source.is_symlink()
        or metadata_source.is_symlink()
        or metadata != installer.with_name(f"{installer.name}.metadata.json")
        or not installer.is_file()
        or installer.stat().st_size != args.size
        or re.fullmatch(r"[0-9a-f]{64}", args.digest) is None
        or args.release_url != (
            f"https://github.com/Oxnight/botw-companion/releases/tag/{parsed.tag}"
        )
        or application.name.casefold() != "botw companion.exe"
        or not application.is_file()
        or not application.with_name("unins000.exe").is_file()
    ):
        _write_relay_state(root, status="failed", version=args.version,
                           message="Le paquet d’installation n’est plus valide.",
                           release_url=args.release_url, can_retry=True, log_available=False,
                           log_path=log_path)
        return 2
    if not _wait_for_parent(args.parent_pid):
        _write_relay_state(root, status="failed", version=args.version,
                           message="BOTW Companion ne s’est pas arrêté dans le délai prévu.",
                           release_url=args.release_url, can_retry=True, log_available=False,
                           log_path=log_path)
        return 3
    if sha256_file(installer) != args.digest:
        _write_relay_state(root, status="failed", version=args.version,
                           message="La vérification de sécurité juste avant installation a échoué.",
                           release_url=args.release_url, can_retry=True, log_available=False,
                           log_path=log_path)
        return 4
    _write_relay_state(root, status="installing", version=args.version,
                       message="L’assistant d’installation Windows est ouvert.",
                       release_url=args.release_url, can_retry=False, log_available=True,
                       log_path=log_path)
    setup_command = [
        str(installer), "/NORESTART", "/CLOSEAPPLICATIONS",
        "/NOFORCECLOSEAPPLICATIONS", "/NORESTARTAPPLICATIONS", "/SP-",
        # Pass one argv value and let CreateProcess quote paths containing spaces.
        # Adding literal quotes here double-quotes the value when subprocess
        # serializes the sequence and makes Inno Setup fail during initialization.
        "/ASSISTEDUPDATE=1", f"/LOG={log_path}",
    ]
    if getattr(args, "silent", False):
        setup_command.extend(("/VERYSILENT", "/SUPPRESSMSGBOXES"))
    setup = subprocess.run(setup_command, shell=False, check=False)
    if setup.returncode != 0:
        message = (
            "Installation annulée. Le paquet vérifié est conservé."
            if setup.returncode in {2, 5}
            else f"L’installation Windows a échoué (code {setup.returncode})."
        )
        _write_relay_state(root, status="cancelled" if setup.returncode in {2, 5} else "failed",
                           version=args.version, message=message,
                           release_url=args.release_url, can_retry=True, log_available=log_path.is_file(),
                           log_path=log_path)
        if application.is_file():
            subprocess.Popen([str(application)], close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                             env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})
        return setup.returncode or 5
    _write_relay_state(root, status="restarting", version=args.version,
                       message="Installation terminée. Vérification du redémarrage…",
                       release_url=args.release_url, can_retry=False, log_available=log_path.is_file(),
                       log_path=log_path)
    subprocess.Popen([str(application)], close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL,
                     creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
                     env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})
    deadline = time.monotonic() + 45.0
    while time.monotonic() < deadline:
        if _probe_version(args.port, args.version):
            installer.unlink(missing_ok=True)
            metadata.unlink(missing_ok=True)
            _write_relay_state(root, status="succeeded", version=args.version,
                               message="BOTW Companion a été mis à jour et redémarré.",
                               release_url=args.release_url, can_retry=False,
                               log_available=log_path.is_file(), log_path=log_path)
            return 0
        time.sleep(0.25)
    _write_relay_state(root, status="failed", version=args.version,
                       message="La nouvelle version est installée mais son redémarrage n’a pas pu être confirmé.",
                       release_url=args.release_url, can_retry=False, log_available=log_path.is_file(),
                       log_path=log_path)
    return 6


def run_relay(args) -> int:
    """Run the relay and preserve actionable diagnostics for unexpected failures."""
    try:
        return _run_relay(args)
    except Exception as exc:
        try:
            root = Path(args.root).resolve()
            diagnostic = root / "logs" / "updater-relay-crash.log"
            diagnostic.parent.mkdir(parents=True, exist_ok=True)
            with diagnostic.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(f"[{int(time.time())}] {type(exc).__name__}: {exc}\n")
                stream.write(traceback.format_exc())
                stream.write("\n")
            _write_relay_state(
                root,
                status="failed",
                version=str(getattr(args, "version", "")),
                message="Le relais Windows a rencontré une erreur inattendue. Consulte le journal de diagnostic.",
                release_url=str(getattr(args, "release_url", "")),
                can_retry=True,
                log_available=True,
                log_path=diagnostic,
            )
        except Exception:
            pass
        return 1
