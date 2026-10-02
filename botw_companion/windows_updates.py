"""Assisted Windows upgrades executed outside the installed application tree."""

from __future__ import annotations

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
import threading
import time
import traceback
import uuid
from urllib.request import ProxyHandler, Request, build_opener

from .persistence import atomic_write_json
from .platforms import companion_data_dir
from .versioning import ReleaseVersion
from .update_downloads import UpdateInstallCandidate


UPDATER_EXE_NAME = "BOTW Companion Updater.exe"
INSTALL_STATE_NAME = "installation.json"
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CHUNK_BYTES = 256 * 1024
RELAY_LOG_PREPARATION_FAILED = 20


class WindowsUpdateError(RuntimeError):
    """A safe, user-facing assisted-upgrade failure."""


WindowsInstallCandidate = UpdateInstallCandidate


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
        self._start_lock = threading.Lock()

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
        # The HTTP server handles requests concurrently, including requests
        # from different browser tabs. Serialize validation and relay creation.
        with self._start_lock:
            return self._start(candidate, parent_pid=parent_pid, port=port)

    def _start(self, candidate: WindowsInstallCandidate, *, parent_pid: int, port: int) -> dict:
        if not self.supported():
            raise WindowsUpdateError(
                "L’installation assistée est disponible uniquement dans l’application Windows installée."
            )
        if self._process is not None and self._process.poll() is None:
            raise WindowsUpdateError("Une installation de mise à jour est déjà en cours")
        parsed = ReleaseVersion.parse(candidate.version)
        if candidate.installer.name != parsed.installer_name:
            raise WindowsUpdateError("Nom d’installateur incohérent")
        if (
            candidate.release_url != (
                f"https://github.com/Oxnight/botw-companion/releases/tag/{parsed.tag}"
            )
            or not _inside_root(candidate.installer, self.root)
            or not _inside_root(candidate.metadata, self.root)
            or candidate.installer.is_symlink()
            or candidate.metadata.is_symlink()
            or candidate.metadata.resolve() != candidate.installer.resolve().with_name(
                f"{candidate.installer.name}.metadata.json"
            )
            or re.fullmatch(r"[0-9a-f]{64}", candidate.digest) is None
            or not candidate.installer.is_file()
            or candidate.installer.stat().st_size != candidate.size
            or sha256_file(candidate.installer) != candidate.digest
            or not _valid_candidate_metadata(candidate)
        ):
            raise WindowsUpdateError("La vérification de sécurité avant installation a échoué")
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
            if self._process.poll() is not None:
                raise OSError("The updater relay exited before the handoff")
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
    if os.name != "nt" or pid == 0:
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
        # A missing process and a process we cannot inspect are different.
        # Access denied must never authorize replacing a running application.
        return ctypes.get_last_error() == 87  # ERROR_INVALID_PARAMETER
    try:
        return kernel32.WaitForSingleObject(handle, int(timeout * 1000)) == wait_object_0
    finally:
        kernel32.CloseHandle(handle)


def _external_process_environment() -> dict[str, str]:
    """Return an environment that does not expose PyInstaller internals."""
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith("_PYI_")
    }
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root and environment.get("PATH"):
        try:
            resolved_bundle = Path(bundle_root).resolve()
            environment["PATH"] = os.pathsep.join(
                entry for entry in environment["PATH"].split(os.pathsep)
                if entry and not _inside_root(Path(entry), resolved_bundle)
            )
        except (OSError, ValueError):
            # SetDllDirectoryW is the primary Windows isolation mechanism. Keep
            # PATH intact if a third-party entry cannot be resolved safely.
            pass
    return environment


def _reset_windows_dll_search_path() -> None:
    """Stop PyInstaller's DLL directory from leaking into external programs."""
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.SetDllDirectoryW.argtypes = (wintypes.LPCWSTR,)
    kernel32.SetDllDirectoryW.restype = wintypes.BOOL
    if not kernel32.SetDllDirectoryW(None):
        raise ctypes.WinError(ctypes.get_last_error())


def _run_external_setup(command: list[str]):
    """Run the independently-built installer with the system DLL search path."""
    _reset_windows_dll_search_path()
    return subprocess.run(
        command,
        shell=False,
        check=False,
        env=_external_process_environment(),
    )


def _prepare_installer_log(log_path: Path) -> None:
    """Create the log directory before Inno Setup parses its /LOG switch."""
    log_path.parent.mkdir(parents=True, exist_ok=True)


def _write_setup_fallback_log(log_path: Path, returncode: int) -> None:
    """Preserve a diagnostic when Setup exits before opening its own log."""
    if log_path.is_file():
        return
    try:
        log_path.write_text(
            "Inno Setup stopped before creating its installation log.\n"
            f"Process exit code: {returncode}\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def _launch_updated_application(application: Path, *, port: int, silent: bool,
                                log_path: Path):
    """Restart the UI for users or the server directly during headless CI."""
    command = [str(application)]
    output = subprocess.DEVNULL
    log_stream = None
    if silent:
        command.extend(("--server", "--port", str(port)))
        try:
            log_stream = log_path.open("ab", buffering=0)
            log_stream.write(b"\n----- BOTW Companion restart diagnostics -----\n")
            output = log_stream
        except OSError:
            if log_stream is not None:
                log_stream.close()
            log_stream = None
    try:
        return subprocess.Popen(
            command,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT if log_stream is not None else subprocess.DEVNULL,
            creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"},
        )
    finally:
        if log_stream is not None:
            log_stream.close()


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
    args._parent_stopped = False
    args._relaunch_attempted = False
    root = Path(args.root).resolve()
    installer_source = Path(args.installer)
    metadata_source = Path(args.metadata)
    installer = installer_source.resolve()
    metadata = metadata_source.resolve()
    application = Path(args.application).resolve()
    log_path = Path(args.log).resolve()
    parsed = ReleaseVersion.parse(args.version)
    candidate = UpdateInstallCandidate(
        version=args.version,
        installer=installer,
        size=args.size,
        digest=args.digest,
        metadata=metadata,
        release_url=args.release_url,
    )
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
        or not _valid_candidate_metadata(candidate)
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
    args._parent_stopped = True
    if sha256_file(installer) != args.digest:
        _write_relay_state(root, status="failed", version=args.version,
                           message="La vérification de sécurité juste avant installation a échoué.",
                           release_url=args.release_url, can_retry=True, log_available=False,
                           log_path=log_path)
        return 4
    try:
        _prepare_installer_log(log_path)
    except OSError:
        _write_relay_state(
            root,
            status="failed",
            version=args.version,
            message="Le dossier du journal d’installation ne peut pas être préparé.",
            release_url=args.release_url,
            can_retry=True,
            log_available=False,
            log_path=log_path,
        )
        return RELAY_LOG_PREPARATION_FAILED
    _write_relay_state(root, status="installing", version=args.version,
                       message="L’assistant d’installation Windows est ouvert.",
                       release_url=args.release_url, can_retry=False, log_available=True,
                       log_path=log_path)
    setup_command = [
        str(installer), "/NORESTART", "/CLOSEAPPLICATIONS",
        "/NOFORCECLOSEAPPLICATIONS", "/NORESTARTAPPLICATIONS", "/SP-",
        # Pass one argv value and let subprocess quote paths containing spaces.
        "/ASSISTEDUPDATE=1", f"/LOG={log_path}",
        f"/DIR={application.parent}",
    ]
    if getattr(args, "silent", False):
        setup_command.extend(("/VERYSILENT", "/SUPPRESSMSGBOXES"))
    setup = _run_external_setup(setup_command)
    if setup.returncode != 0:
        _write_setup_fallback_log(log_path, setup.returncode)
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
            _launch_updated_application(
                application,
                port=args.port,
                silent=False,
                log_path=log_path,
            )
            args._relaunch_attempted = True
        return setup.returncode or 5
    _write_relay_state(root, status="restarting", version=args.version,
                       message="Installation terminée. Vérification du redémarrage…",
                       release_url=args.release_url, can_retry=False, log_available=log_path.is_file(),
                       log_path=log_path)
    silent_restart = bool(getattr(args, "silent", False))
    restarted = _launch_updated_application(
        application,
        port=args.port,
        silent=silent_restart,
        log_path=log_path,
    )
    args._relaunch_attempted = True
    deadline = time.monotonic() + 45.0
    restart_exit_code = None
    while time.monotonic() < deadline:
        if _probe_version(args.port, args.version):
            installer.unlink(missing_ok=True)
            metadata.unlink(missing_ok=True)
            _write_relay_state(root, status="succeeded", version=args.version,
                               message="BOTW Companion a été mis à jour et redémarré.",
                               release_url=args.release_url, can_retry=False,
                               log_available=log_path.is_file(), log_path=log_path)
            return 0
        if silent_restart:
            restart_exit_code = restarted.poll()
            if restart_exit_code is not None:
                break
        time.sleep(0.25)
    message = "La nouvelle version est installée mais son redémarrage n’a pas pu être confirmé."
    if restart_exit_code is not None:
        message = (
            "La nouvelle version est installée mais son serveur de validation "
            f"s’est arrêté (code {restart_exit_code})."
        )
    _write_relay_state(root, status="failed", version=args.version,
                       message=message,
                       release_url=args.release_url, can_retry=True, log_available=log_path.is_file(),
                       log_path=log_path)
    return 6


def _recover_stopped_application(args) -> None:
    if (not getattr(args, "_parent_stopped", False)
            or getattr(args, "_relaunch_attempted", False)):
        return
    try:
        application = Path(args.application).resolve()
        if application.is_file():
            _launch_updated_application(
                application, port=args.port,
                silent=bool(getattr(args, "silent", False)),
                log_path=Path(args.log).resolve(),
            )
            args._relaunch_attempted = True
    except Exception:
        # Preserve the installation error and its diagnostic even if Windows
        # cannot reopen the installed application automatically.
        pass


def run_relay(args) -> int:
    """Run the relay and preserve actionable diagnostics for unexpected failures."""
    try:
        result = _run_relay(args)
        if result != 0:
            _recover_stopped_application(args)
        return result
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
        _recover_stopped_application(args)
        return 1
