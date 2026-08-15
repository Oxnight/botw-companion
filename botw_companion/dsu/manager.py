from __future__ import annotations

from importlib.resources import files
import os
from pathlib import Path
import platform
import socket
import struct
import subprocess
import threading
import time
import zlib

from ..platforms import companion_data_dir


DSU_HOST = "127.0.0.1"
DSU_PORT = 26760
DSU_PROTOCOL_VERSION = 1001
DSU_MSG_PORTS = 0x100001


def _client_packet(message_type: int, payload: bytes = b"") -> bytes:
    packet = bytearray(20 + len(payload))
    packet[:4] = b"DSUC"
    struct.pack_into("<H", packet, 4, DSU_PROTOCOL_VERSION)
    struct.pack_into("<H", packet, 6, len(packet) - 16)
    struct.pack_into("<I", packet, 12, 0x42545743)
    struct.pack_into("<I", packet, 16, message_type)
    packet[20:] = payload
    struct.pack_into("<I", packet, 8, zlib.crc32(packet) & 0xFFFFFFFF)
    return bytes(packet)


def probe_dsu(timeout: float = 0.2) -> dict | None:
    """Interroge réellement le port 0 DSU; aucun état n'est déduit du PID."""
    request = _client_packet(DSU_MSG_PORTS, struct.pack("<IB", 1, 0))
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(timeout)
            client.sendto(request, (DSU_HOST, DSU_PORT))
            response, sender = client.recvfrom(256)
    except (OSError, TimeoutError):
        return None

    if sender[0] != DSU_HOST or len(response) < 32 or response[:4] != b"DSUS":
        return None
    if struct.unpack_from("<I", response, 16)[0] != DSU_MSG_PORTS:
        return None

    expected_crc = struct.unpack_from("<I", response, 8)[0]
    checked = bytearray(response)
    struct.pack_into("<I", checked, 8, 0)
    if zlib.crc32(checked) & 0xFFFFFFFF != expected_crc:
        return None

    return {
        "slot": response[20],
        "connected": response[21] == 2,
        "motion": response[22] == 2,
    }


class DsuManager:
    """Possède le processus JoyConDSU pendant toute la vie du serveur web."""

    def __init__(self, *, executable: Path | None = None,
                 launcher: Path | None = None, system: str | None = None,
                 machine: str | None = None, support_dir: Path | None = None,
                 sdl_library: Path | None = None,
                 probe=probe_dsu, popen=subprocess.Popen) -> None:
        resource_root = files("botw_companion.dsu")
        self.executable = executable or Path(str(resource_root.joinpath("JoyConDSU")))
        self.launcher = launcher or Path(str(resource_root.joinpath("launch_managed.sh")))
        self.system = system or platform.system()
        self.machine = (machine or platform.machine()).lower()
        self.support_dir = support_dir or companion_data_dir(system=self.system)
        self.log_path = self.support_dir / "joycon-dsu.log"
        self.sdl_library = sdl_library or Path(
            "/opt/homebrew/opt/sdl3/lib/libSDL3.0.dylib"
        )
        self._probe = probe
        self._popen = popen
        self._process = None
        self._log_handle = None
        self._lock = threading.RLock()
        self._last_error: str | None = None
        self._started_at: float | None = None

    def _availability_error(self) -> str | None:
        if self.system != "Darwin":
            return "JoyConDSU intégré est disponible uniquement sur macOS."
        if not self.executable.is_file():
            return "Le binaire JoyConDSU est absent du paquet."
        if not self.launcher.is_file():
            return "Le lanceur supervisé JoyConDSU est absent du paquet."
        if not self.sdl_library.is_file():
            return "SDL3 est requis : installe-le avec « brew install sdl3 »."
        return None

    def _rotate_log(self) -> None:
        self.support_dir.mkdir(parents=True, exist_ok=True)
        if self.log_path.is_file() and self.log_path.stat().st_size > 500_000:
            data = self.log_path.read_bytes()[-200_000:]
            self.log_path.write_bytes(data)

    def _tail_error(self) -> str:
        try:
            text = self.log_path.read_text(errors="replace")[-3000:]
        except OSError:
            return "JoyConDSU s’est arrêté avant de devenir disponible."
        useful = [line.strip() for line in text.splitlines() if line.strip()]
        return useful[-1] if useful else "JoyConDSU s’est arrêté avant de devenir disponible."

    def _refresh_process(self) -> bool:
        if self._process is None:
            return False
        code = self._process.poll()
        if code is None:
            return True
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None
        self._process = None
        if code != 0 and self._last_error is None:
            self._last_error = self._tail_error()
        return False

    def status(self) -> dict:
        with self._lock:
            running = self._refresh_process()
            availability_error = self._availability_error()

            if not running:
                if self._last_error:
                    state, label, message = "error", "Erreur DSU", self._last_error
                elif availability_error:
                    state, label, message = "unavailable", "DSU indisponible", availability_error
                else:
                    state, label, message = (
                        "off", "Gyroscope Joy-Con désactivé",
                        "Active-le uniquement lorsque tu joues avec les deux Joy-Con."
                    )
                return self._payload(state, label, message, False, False)

            probe = self._probe()
            if probe and probe["connected"] and probe["motion"]:
                return self._payload(
                    "ready", "Gyroscope Joy-Con prêt",
                    "Mouvements transmis à Ryujinx sur 127.0.0.1:26760.", True, True,
                )
            if probe is not None:
                return self._payload(
                    "waiting_controller", "En attente des Joy-Con",
                    "Connecte la paire L/R puis pose le grip immobile pendant la calibration.",
                    True, False,
                )
            return self._payload(
                "starting", "Démarrage et calibration DSU",
                "Laisse le grip immobile quelques secondes pendant l’initialisation.", True, False,
            )

    def _payload(self, state: str, label: str, message: str,
                 running: bool, controller_connected: bool) -> dict:
        return {
            "schema_version": 1,
            "state": state,
            "state_label": label,
            "message": message,
            "running": running,
            "controller_connected": controller_connected,
            "host": DSU_HOST,
            "port": DSU_PORT,
            "enabled_by_default": False,
            "started_at": self._started_at,
        }

    def start(self) -> dict:
        with self._lock:
            if self._refresh_process():
                return self.status()
            self._last_error = None
            error = self._availability_error()
            if error:
                self._last_error = error
                return self.status()
            if self._probe() is not None:
                self._last_error = (
                    "Le port 26760 est déjà utilisé par un autre serveur DSU local. "
                    "Arrête-le avant d’activer celui du Companion."
                )
                return self.status()

            self._rotate_log()
            self._log_handle = self.log_path.open("ab", buffering=0)
            try:
                self._process = self._popen(
                    [str(self.launcher), str(self.executable), str(os.getpid())],
                    stdin=subprocess.DEVNULL,
                    stdout=self._log_handle,
                    stderr=subprocess.STDOUT,
                    close_fds=True,
                )
            except OSError as exc:
                self._log_handle.close()
                self._log_handle = None
                self._last_error = f"Démarrage impossible : {exc}"
                return self.status()
            self._started_at = time.time()

        # Laisse au binaire le temps d'ouvrir le socket, sans bloquer l'UI longtemps.
        for _attempt in range(8):
            time.sleep(0.1)
            with self._lock:
                if not self._refresh_process() or self._probe() is not None:
                    break
        return self.status()

    def stop(self) -> dict:
        with self._lock:
            process = self._process
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            if self._log_handle is not None:
                self._log_handle.close()
                self._log_handle = None
            self._process = None
            self._started_at = None
            self._last_error = None
            return self.status()

    def close(self) -> None:
        self.stop()