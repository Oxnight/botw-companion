from __future__ import annotations

import argparse
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


class LauncherError(RuntimeError):
    pass


def load_config(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LauncherError(f"Configuration macOS invalide : {exc}") from exc
    if not isinstance(value, dict):
        raise LauncherError("La configuration macOS doit être un objet JSON")
    return value


def port_available(port: int) -> bool:
    try:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


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


def server_command(executable: Path, project_root: Path, port: int,
                   config: Mapping[str, object], *, frozen: bool) -> list[str]:
    command = (
        [str(executable), "--server"]
        if frozen
        else [str(executable), "-m", "botw_companion", "interface"]
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
        "--arreter-avec-emulateur",
    ])
    return command


def launch_server(executable: Path, project_root: Path, port: int,
                  config: Mapping[str, object], log_path: Path, *,
                  popen=subprocess.Popen, frozen: bool):
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
    if frozen:
        environment["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab", buffering=0) as log:
        return popen(
            server_command(executable, project_root, port, config, frozen=frozen),
            cwd=project_root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            close_fds=True,
            start_new_session=True,
        )


def open_default_browser(url: str) -> bool:
    if sys.platform == "darwin":
        return subprocess.run(
            ["/usr/bin/open", url],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0
    return bool(webbrowser.open(url, new=0, autoraise=True))


def show_error(message: str, *, runner=subprocess.run) -> None:
    if sys.platform != "darwin":
        return
    runner(
        [
            "/usr/bin/osascript",
            "-e",
            'on run argv\ndisplay alert "BOTW Companion" message (item 1 of argv) as critical\nend run',
            "--",
            message,
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def run(*, config_path: Path | None = None,
        probe=probe_companion_server,
        browser=open_default_browser,
        popen=subprocess.Popen,
        frozen: bool | None = None) -> int:
    data_root = companion_data_dir(system="Darwin")
    config = load_config(config_path or data_root / "launcher.json")
    port = int(config.get("port", DEFAULT_PORT))
    if not 1 <= port <= 65535:
        raise LauncherError("Le port configuré doit être compris entre 1 et 65535")
    url = f"http://127.0.0.1:{port}"
    identity = probe(port, timeout=0.5)
    if identity is not None:
        if identity.get("version") == __version__:
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
    executable = Path(sys.executable).resolve()
    project_root = executable.parent if packaged else Path(__file__).resolve().parents[1]
    process = launch_server(
        executable,
        project_root,
        port,
        config,
        data_root / "launcher.log",
        popen=popen,
        frozen=packaged,
    )
    wait_until_ready(port, __version__, process, probe=probe)
    browser(url)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", type=Path)
    args, unknown = parser.parse_known_args(argv)
    unexpected = [value for value in unknown if not value.startswith("-psn_")]
    data_root = companion_data_dir(system="Darwin")
    log_path = data_root / "launcher.log"
    try:
        if unexpected:
            raise LauncherError(f"Option de lancement inconnue : {unexpected[0]}")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=log_path,
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            encoding="utf-8",
        )
        logging.info("Lancement de BOTW Companion %s", __version__)
        return run(config_path=args.config)
    except Exception as exc:
        logging.exception("Échec du lanceur macOS")
        show_error(
            f"BOTW Companion ne peut pas démarrer.\n\n{exc}\n\n"
            f"Journal : {log_path}"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
