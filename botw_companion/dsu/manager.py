from __future__ import annotations

from importlib.resources import files
import math
import os
from pathlib import Path
import platform
import socket
import struct
import subprocess
import threading
import time
import zlib

from ..platforms import companion_data_dir, platform_label
from .windows_runtime import signal_stop_event


DSU_HOST = "127.0.0.1"
DSU_PORT = 26760
DSU_PROTOCOL_VERSION = 1001
DSU_MSG_PORTS = 0x100001
WINDOWS_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
TELEMETRY_PREFIX = "BOTW_DSU_TELEMETRY\t"
TELEMETRY_FLOAT_FIELDS = {
    "uptime_s", "received_hz", "sent_hz", "sample_age_ms",
    "received_jitter_mean_ms", "received_jitter_max_ms",
    "sent_jitter_mean_ms", "sent_jitter_max_ms",
}
TELEMETRY_INT_FIELDS = {
    "version", "clients", "sensor_events", "paired_samples",
    "duplicate_timestamps", "regressive_timestamps", "fallback_timestamps",
    "invalid_values", "sent_packets", "requests", "invalid_requests",
    "send_errors", "stale_samples", "nonfinite_samples", "disconnects",
    "reconnects", "calibrations_valid", "calibrations_rejected",
    "calibration_valid",
}


def _windows_runtime_directory(resource_root: Path, *,
                               environ=None,
                               project_root: Path | None = None) -> Path:
    values = os.environ if environ is None else environ
    override = values.get("BOTW_COMPANION_DSU_DIR")
    if override:
        return Path(override).expanduser()
    project = project_root or Path(__file__).resolve().parents[2]
    candidates = [
        resource_root / "windows",
        project / "windows" / "native-dsu",
    ]
    for candidate in candidates:
        if (candidate / "JoyConDSU.exe").is_file() \
                and (candidate / "SDL3.dll").is_file():
            return candidate
    return candidates[0]


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
                 runtime_dir: Path | None = None, environ=None,
                 probe=probe_dsu, popen=subprocess.Popen,
                 run=subprocess.run,
                 windows_stop_signal=signal_stop_event) -> None:
        resource_root = Path(str(files("botw_companion.dsu")))
        self.system = system or platform.system()
        self.machine = (machine or platform.machine()).lower()
        if self.system == "Windows":
            self.runtime_dir = runtime_dir or _windows_runtime_directory(
                resource_root,
                environ=environ,
            )
            self.executable = executable or self.runtime_dir / "JoyConDSU.exe"
            self.sdl_library = sdl_library or self.executable.parent / "SDL3.dll"
        elif self.system == "Darwin":
            self.runtime_dir = resource_root / "macos"
            self.executable = executable or self.runtime_dir / "JoyConDSU"
            self.sdl_library = sdl_library or self.runtime_dir / "libSDL3.0.dylib"
        else:
            self.runtime_dir = resource_root
            self.executable = executable or resource_root / "JoyConDSU"
            self.sdl_library = sdl_library or resource_root / "libSDL3.0.dylib"
        self.launcher = launcher or self.runtime_dir / "launch_managed.sh"
        self.support_dir = support_dir or companion_data_dir(system=self.system)
        self.log_path = self.support_dir / "joycon-dsu.log"
        self._probe = probe
        self._popen = popen
        self._run = run
        self._windows_stop_signal = windows_stop_signal
        self._process = None
        self._log_handle = None
        self._lock = threading.RLock()
        self._last_error: str | None = None
        self._started_at: float | None = None
        self._selected_source: dict | None = None
        self._controller_cache: list[dict] = []
        self._controller_cache_at = 0.0

    def _availability_error(self) -> str | None:
        if self.system == "Windows":
            if not self.executable.is_file():
                return "Le moteur JoyConDSU.exe est absent du paquet Windows."
            if not self.sdl_library.is_file():
                return "SDL3.dll doit se trouver à côté de JoyConDSU.exe."
            return None
        if self.system != "Darwin":
            return "Le moteur JoyConDSU intégré n’est pas disponible sur ce système."
        if not self.executable.is_file():
            return "Le binaire JoyConDSU est absent du paquet."
        if not self.launcher.is_file():
            return "Le lanceur supervisé JoyConDSU est absent du paquet."
        if not self.sdl_library.is_file():
            return "La bibliothèque SDL3 intégrée est absente du paquet."
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

    @staticmethod
    def _parse_controller_inventory(output: str) -> list[dict]:
        controllers: list[dict] = []
        for line in output.splitlines():
            if not line.startswith("CONTROLLER\t"):
                continue
            parts = line.split("\t", 9)
            if len(parts) != 10:
                continue
            try:
                instance_id = int(parts[1])
                vendor_id = int(parts[2])
                product_id = int(parts[3])
                type_id = int(parts[4])
                gyro = parts[5] == "1"
                accel = parts[6] == "1"
            except ValueError:
                continue
            type_name, name, path = parts[7], parts[8], parts[9]
            kind = (
                "joycon_pair"
                if type_name == "joyconpair"
                else "joycon_single"
                if type_name in {"joyconleft", "joyconright"}
                else "gamepad"
            )
            source_id = (
                f"path:{path}"
                if path else
                f"device:{vendor_id:04x}:{product_id:04x}:{type_id}:{name}"
            )
            controllers.append({
                "id": source_id,
                "instance_id": instance_id,
                "name": name or "Contrôleur inconnu",
                "type": type_name or "unknown",
                "type_id": type_id,
                "vendor_id": vendor_id,
                "product_id": product_id,
                "path": path,
                "gyro": gyro,
                "accelerometer": accel,
                "compatible": gyro and accel and kind != "joycon_single",
                "kind": kind,
            })
        controllers.sort(
            key=lambda item: (
                0 if item["kind"] == "joycon_pair" else 1,
                0 if item["compatible"] else 1,
                item["name"].lower(),
                item["id"],
            )
        )
        return controllers

    def _inventory_command(self) -> tuple[list[str], dict]:
        if self.system == "Windows":
            options = {"cwd": self.executable.parent}
            if os.name == "nt":
                options["creationflags"] = WINDOWS_CREATE_NO_WINDOW
            return [str(self.executable), "--list-controllers"], options
        return [
            str(self.launcher),
            str(self.executable),
            str(os.getpid()),
            "--list-controllers",
        ], {}

    def controllers(self, *, force: bool = False) -> list[dict]:
        with self._lock:
            if self._refresh_process():
                return list(self._controller_cache)
            if self._availability_error():
                return []
            now = time.monotonic()
            if not force and now - self._controller_cache_at < 3.0:
                return list(self._controller_cache)
            command, options = self._inventory_command()
            try:
                result = self._run(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=8,
                    close_fds=True,
                    **options,
                )
            except (OSError, subprocess.SubprocessError):
                self._controller_cache = []
                self._controller_cache_at = now
                return []
            if result.returncode != 0:
                self._controller_cache = []
                self._controller_cache_at = now
                return []
            self._controller_cache = self._parse_controller_inventory(result.stdout)
            self._controller_cache_at = now
            return list(self._controller_cache)

    def _resolve_source(self, source_id: str | None) -> dict | None:
        controllers = self.controllers(force=True)
        if source_id:
            return next((item for item in controllers if item["id"] == str(source_id)), None)
        return next((item for item in controllers if item["compatible"]), None)

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
                        "off", "Gyroscope désactivé",
                        "Choisis une manette avec gyroscope puis active le serveur DSU."
                    )
                return self._payload(state, label, message, False, False)

            probe = self._probe()
            if probe and probe["connected"] and probe["motion"]:
                return self._payload(
                    "ready", "Gyroscope prêt",
                    "Mouvements transmis à l’émulateur sur 127.0.0.1:26760.", True, True,
                )
            if probe is not None:
                return self._payload(
                    "waiting_controller", "En attente de la manette",
                    "Reconnecte la source sélectionnée puis laisse-la immobile pendant la calibration.",
                    True, False,
                )
            return self._payload(
                "starting", "Démarrage et calibration DSU",
                "Laisse la manette immobile quelques secondes pendant l’initialisation.", True, False,
            )

    @staticmethod
    def _parse_telemetry_line(line: str) -> dict | None:
        if not line.startswith(TELEMETRY_PREFIX):
            return None
        result: dict = {}
        for part in line[len(TELEMETRY_PREFIX):].strip().split("\t"):
            key, separator, raw = part.partition("=")
            if not separator or not key:
                continue
            try:
                if key in TELEMETRY_FLOAT_FIELDS:
                    value = float(raw)
                    if not math.isfinite(value):
                        return None
                    result[key] = value
                elif key in TELEMETRY_INT_FIELDS:
                    result[key] = int(raw)
                else:
                    result[key] = raw
            except ValueError:
                return None
        if result.get("version") != 1 or "health" not in result:
            return None
        return result

    def _telemetry_snapshot(self, running: bool) -> dict | None:
        if not running or not self.log_path.is_file():
            return None
        try:
            stat = self.log_path.stat()
            if self._started_at is not None and stat.st_mtime < self._started_at - 1.0:
                return None
            with self.log_path.open("rb") as handle:
                handle.seek(max(0, stat.st_size - 65_536))
                tail = handle.read().decode("utf-8", errors="replace")
        except OSError:
            return None
        for line in reversed(tail.splitlines()):
            parsed = self._parse_telemetry_line(line)
            if parsed is not None:
                parsed["measurement_age_seconds"] = max(0.0, time.time() - stat.st_mtime)
                return parsed
        return None

    @staticmethod
    def _diagnostic(state: str, running: bool, telemetry: dict | None) -> dict:
        if not running:
            return {
                "status": "inactive",
                "label": "Diagnostic inactif",
                "summary": "Active le gyroscope pour mesurer la qualité du signal.",
            }
        if telemetry is None:
            return {
                "status": "collecting",
                "label": "Mesure en cours",
                "summary": "Le premier diagnostic apparaîtra après quelques secondes.",
            }
        if not telemetry.get("calibration_valid"):
            return {
                "status": "recalibration",
                "label": "Recalibration recommandée",
                "summary": "La calibration n’est pas valide. Immobilise la manette et relance le gyroscope.",
            }
        if state != "ready":
            return {
                "status": "collecting",
                "label": "Mesure en cours",
                "summary": "Le contrôleur doit être prêt avant d’évaluer le signal.",
            }

        received = telemetry.get("received_hz", 0.0)
        sent = telemetry.get("sent_hz", 0.0)
        clients = telemetry.get("clients", 0)
        age = telemetry.get("sample_age_ms", -1.0)
        measurement_age = telemetry.get("measurement_age_seconds", 0.0)
        receive_mean = telemetry.get("received_jitter_mean_ms", 0.0)
        receive_max = telemetry.get("received_jitter_max_ms", 0.0)
        sent_mean = telemetry.get("sent_jitter_mean_ms", 0.0)
        sent_max = telemetry.get("sent_jitter_max_ms", 0.0)
        events = max(1, telemetry.get("sensor_events", 0))
        packets = max(1, telemetry.get("sent_packets", 0))
        timestamp_ratio = (
            telemetry.get("duplicate_timestamps", 0)
            + telemetry.get("regressive_timestamps", 0)
        ) / events
        invalid_ratio = (
            telemetry.get("invalid_values", 0)
            + telemetry.get("nonfinite_samples", 0)
        ) / events
        send_error_ratio = telemetry.get("send_errors", 0) / packets
        sending_excellent = clients == 0 or 170.0 <= sent <= 230.0
        sending_correct = clients == 0 or 120.0 <= sent <= 260.0

        excellent = all((
            telemetry.get("health") == "ok",
            measurement_age <= 15.0,
            170.0 <= received <= 230.0,
            sending_excellent,
            0.0 <= age <= 20.0,
            receive_mean <= 1.5,
            receive_max <= 20.0,
            clients == 0 or sent_mean <= 1.5,
            clients == 0 or sent_max <= 20.0,
            timestamp_ratio <= 0.001,
            invalid_ratio <= 0.0001,
            send_error_ratio <= 0.0001,
        ))
        correct = all((
            telemetry.get("health") == "ok",
            measurement_age <= 25.0,
            120.0 <= received <= 260.0,
            sending_correct,
            0.0 <= age <= 50.0,
            receive_mean <= 4.0,
            receive_max <= 50.0,
            clients == 0 or sent_mean <= 4.0,
            clients == 0 or sent_max <= 50.0,
            timestamp_ratio <= 0.01,
            invalid_ratio <= 0.001,
            send_error_ratio <= 0.001,
        ))
        if excellent:
            return {
                "status": "excellent",
                "label": "Excellent",
                "summary": "Signal régulier, récent et transmis sans anomalie notable.",
            }
        if correct:
            return {
                "status": "correct",
                "label": "Correct",
                "summary": "Signal exploitable avec de légères variations sans impact attendu en jeu.",
            }
        return {
            "status": "unstable",
            "label": "Instable",
            "summary": "La cadence, le jitter ou les erreurs mesurées dépassent les seuils recommandés.",
        }

    def _payload(self, state: str, label: str, message: str,
                 running: bool, controller_connected: bool) -> dict:
        engine_name = "JoyConDSU.exe" if self.system == "Windows" else self.executable.name
        controllers = list(self._controller_cache)
        if not running and self._availability_error() is None:
            controllers = self.controllers()
        telemetry = self._telemetry_snapshot(running)
        return {
            "schema_version": 3,
            "state": state,
            "state_label": label,
            "message": message,
            "running": running,
            "controller_connected": controller_connected,
            "host": DSU_HOST,
            "port": DSU_PORT,
            "enabled_by_default": False,
            "started_at": self._started_at,
            "platform": platform_label(self.system),
            "engine_name": engine_name,
            "log_path": str(self.log_path),
            "controllers": controllers,
            "selected_source": self._selected_source,
            "diagnostic": self._diagnostic(state, running, telemetry),
            "telemetry": telemetry,
        }

    def start(self, source_id: str | None = None) -> dict:
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

            source = self._resolve_source(source_id)
            if source_id and source is None:
                self._last_error = "La manette sélectionnée n’est plus connectée."
                return self.status()
            if source is not None and not source["compatible"]:
                self._last_error = (
                    f"« {source['name']} » n’expose pas un gyroscope et un "
                    "accéléromètre compatibles."
                )
                self._selected_source = source
                return self.status()
            self._selected_source = source

            self._rotate_log()
            self._log_handle = self.log_path.open("ab", buffering=0)
            if source is None:
                source_args = []
            elif source.get("path"):
                source_args = ["--controller-path", source["path"]]
            else:
                source_args = ["--controller-id", str(source["instance_id"])]
            if self.system == "Windows":
                command = [str(self.executable), *source_args]
                launch_options = {
                    "cwd": self.executable.parent,
                    "creationflags": WINDOWS_CREATE_NO_WINDOW,
                }
            else:
                command = [
                    str(self.launcher),
                    str(self.executable),
                    str(os.getpid()),
                    *source_args,
                ]
                launch_options = {}
            try:
                self._process = self._popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=self._log_handle,
                    stderr=subprocess.STDOUT,
                    close_fds=True,
                    **launch_options,
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
                cooperatively_stopped = False
                if self.system == "Windows" and getattr(process, "pid", 0):
                    try:
                        cooperatively_stopped = bool(
                            self._windows_stop_signal(process.pid)
                        )
                    except OSError:
                        cooperatively_stopped = False
                    if cooperatively_stopped:
                        try:
                            process.wait(timeout=4)
                        except subprocess.TimeoutExpired:
                            pass
                if process.poll() is None:
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
