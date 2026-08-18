from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Callable, Mapping
from urllib.request import Request, urlopen
import webbrowser

from . import __version__
from .lifecycle import probe_companion_server
from .platforms import companion_data_dir


DEFAULT_PORT = 8765
DEFAULT_READY_TIMEOUT = 30.0
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
SW_RESTORE = 9


class LauncherError(RuntimeError):
    pass


def _is_project_root(path: Path) -> bool:
    return (
        path.joinpath("pyproject.toml").is_file()
        and path.joinpath("botw_companion").is_dir()
    )


def load_config(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LauncherError(f"Configuration Windows invalide : {exc}") from exc
    if not isinstance(value, dict):
        raise LauncherError("La configuration Windows doit être un objet JSON")
    return value


def find_project_root(explicit: str | None, config: Mapping[str, object], *,
                      environ: Mapping[str, str] | None = None,
                      current: Path | None = None) -> Path:
    values = os.environ if environ is None else environ
    candidates = [
        explicit,
        values.get("BOTW_COMPANION_PROJECT"),
        config.get("project_root"),
        current or Path.cwd(),
        Path(__file__).resolve().parents[1],
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(str(candidate)).expanduser().resolve()
        if _is_project_root(path):
            return path
    raise LauncherError(
        "Installation BOTW Companion introuvable. Relance l’installeur Windows "
        "depuis le dossier du projet."
    )


def find_python(project_root: Path, config: Mapping[str, object], *,
                environ: Mapping[str, str] | None = None,
                current_executable: str | None = None) -> Path:
    values = os.environ if environ is None else environ
    configured = values.get("BOTW_COMPANION_PYTHON") or config.get("python_executable")
    candidates = [
        configured,
        project_root / "runtime" / "pythonw.exe",
        project_root / "python" / "pythonw.exe",
        project_root / ".venv" / "Scripts" / "pythonw.exe",
        current_executable or sys.executable,
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(str(candidate)).expanduser().resolve()
        if path.is_file() and path.name.casefold() in {"pythonw.exe", "python.exe"}:
            return path
    raise LauncherError(
        "Python Windows introuvable. Installe le runtime embarqué ou recrée "
        "l’environnement .venv avant de relancer l’installeur."
    )


def focus_companion_window(*, user32=None,
                           title_fragment: str = "BOTW Companion") -> bool:
    if os.name != "nt" and user32 is None:
        return False
    api = user32 or ctypes.WinDLL("user32", use_last_error=True)
    callback_type = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(
        ctypes.c_bool,
        ctypes.c_void_p,
        ctypes.c_void_p,
    )
    found: list[int] = []

    def inspect(hwnd, _lparam) -> bool:
        if not api.IsWindowVisible(hwnd):
            return True
        length = api.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        api.GetWindowTextW(hwnd, buffer, len(buffer))
        if title_fragment.casefold() in buffer.value.casefold():
            found.append(hwnd)
            return False
        return True

    callback = callback_type(inspect)
    api.EnumWindows(callback, 0)
    if not found:
        return False
    api.ShowWindow(found[0], SW_RESTORE)
    return bool(api.SetForegroundWindow(found[0]))


def open_default_browser(url: str) -> bool:
    if os.name == "nt" and hasattr(os, "startfile"):
        os.startfile(url)
        return True
    return bool(webbrowser.open(url, new=0, autoraise=True))


def request_shutdown(port: int, *, opener=urlopen) -> bool:
    try:
        with opener(Request(
            f"http://127.0.0.1:{port}/api/shutdown",
            data=b"",
            method="POST",
        ), timeout=1.5) as response:
            return getattr(response, "status", 200) == 200
    except OSError:
        return False


def port_available(port: int) -> bool:
    try:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


def wait_until_stopped(port: int, timeout: float = 8.0, *,
                       probe=probe_companion_server,
                       clock: Callable[[], float] = time.monotonic,
                       sleep: Callable[[float], None] = time.sleep) -> bool:
    deadline = clock() + timeout
    while clock() < deadline:
        if probe(port, timeout=0.2) is None and port_available(port):
            return True
        sleep(0.1)
    return False


def wait_until_ready(port: int, expected_version: str, process, *,
                     timeout: float = DEFAULT_READY_TIMEOUT,
                     probe=probe_companion_server,
                     clock: Callable[[], float] = time.monotonic,
                     sleep: Callable[[float], None] = time.sleep) -> dict:
    deadline = clock() + timeout
    while clock() < deadline:
        identity = probe(port, timeout=0.3)
        if identity is not None:
            if identity.get("version") != expected_version:
                raise LauncherError(
                    "Une autre version de BOTW Companion utilise encore le port local"
                )
            return identity
        if process.poll() is not None:
            raise LauncherError(
                "Le serveur BOTW Companion s’est arrêté pendant son démarrage"
            )
        sleep(0.15)
    raise LauncherError("Le serveur BOTW Companion n’a pas répondu dans le délai prévu")


def server_command(python: Path, project_root: Path, port: int,
                   config: Mapping[str, object], *, frozen: bool = False) -> list[str]:
    command = (
        [str(python), "--server"]
        if frozen
        else [str(python), "-m", "botw_companion", "interface"]
    )
    save_path = config.get("save_path")
    if save_path:
        if frozen:
            command.extend(["--save-path", str(save_path)])
        else:
            command.append(str(save_path))
    command.extend([
        "--port",
        str(port),
        "--sans-navigateur",
        "--arreter-avec-ryujinx",
    ])
    return command


def launch_server(python: Path, project_root: Path, port: int,
                  config: Mapping[str, object], log_path: Path, *,
                  popen=subprocess.Popen, frozen: bool = False):
    environment = os.environ.copy()
    for config_key, env_key in (
        ("ryujinx_process_names", "BOTW_RYUJINX_PROCESS_NAMES"),
        ("cemu_process_names", "BOTW_CEMU_PROCESS_NAMES"),
    ):
        names = config.get(config_key)
        if isinstance(names, list):
            cleaned = [str(name).strip() for name in names if str(name).strip()]
            if cleaned:
                environment[env_key] = ";".join(cleaned)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab", buffering=0) as log:
        return popen(
            server_command(python, project_root, port, config, frozen=frozen),
            cwd=project_root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=(
                CREATE_NO_WINDOW
                | DETACHED_PROCESS
                | CREATE_NEW_PROCESS_GROUP
            ),
            close_fds=True,
        )


def show_error(message: str, *, user32=None) -> None:
    if os.name != "nt" and user32 is None:
        return
    api = user32 or ctypes.WinDLL("user32", use_last_error=True)
    api.MessageBoxW(
        None,
        message,
        "BOTW Companion",
        0x00000010 | 0x00010000 | 0x00040000,
    )


def run(*, explicit_project: str | None = None,
        config_path: Path | None = None,
        probe=probe_companion_server,
        focus=focus_companion_window,
        browser=open_default_browser,
        popen=subprocess.Popen,
        frozen: bool | None = None) -> int:
    data_root = companion_data_dir(system="Windows")
    path = config_path or data_root / "launcher.json"
    config = load_config(path)
    port = int(config.get("port", DEFAULT_PORT))
    if not 1 <= port <= 65535:
        raise LauncherError("Le port configuré doit être compris entre 1 et 65535")
    url = f"http://127.0.0.1:{port}"
    identity = probe(port, timeout=0.5)
    if identity is not None:
        if identity.get("version") == __version__:
            if not focus():
                browser(url)
            return 0
        if not request_shutdown(port) or not wait_until_stopped(port, probe=probe):
            raise LauncherError(
                "L’ancienne version du Companion n’a pas pu être arrêtée proprement"
            )
    elif not port_available(port):
        raise LauncherError(
            f"Le port local {port} est déjà occupé par une autre application"
        )
    packaged = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if packaged:
        python = Path(sys.executable).resolve()
        project_root = python.parent
    else:
        project_root = find_project_root(explicit_project, config)
        python = find_python(project_root, config)
    log_path = data_root / "launcher.log"
    process = launch_server(
        python,
        project_root,
        port,
        config,
        log_path,
        popen=popen,
        frozen=packaged,
    )
    wait_until_ready(port, __version__, process, probe=probe)
    browser(url)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project")
    parser.add_argument("--config", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data_root = companion_data_dir(system="Windows")
    log_path = data_root / "launcher.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=log_path,
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            encoding="utf-8",
        )
        logging.info("Lancement de BOTW Companion %s", __version__)
        return run(explicit_project=args.project, config_path=args.config)
    except Exception as exc:
        logging.exception("Échec du lanceur Windows")
        show_error(
            f"BOTW Companion ne peut pas démarrer.\n\n{exc}\n\n"
            f"Journal : {log_path}"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())