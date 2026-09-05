from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from botw_companion.analyzer import analyze
from botw_companion.blood_moon import blood_moon_status
from botw_companion.manual_tracking import ManualTrackingStore
from botw_companion.preferences import PreferenceStore
from botw_companion.route_sessions import RouteSessionStore
from botw_companion.runtime_state import RuntimeStateStore
from botw_companion.server import serve


class BrowserTestSync:
    def __init__(self, report: dict) -> None:
        self._report = report

    def report(self, force: bool = False) -> dict:
        return self._report

    def check(self, force: bool = False, include_report: bool = False) -> dict:
        payload = {
            "changed": False,
            "synchronisation": self._report["synchronisation"],
        }
        if include_report:
            payload["report"] = self._report
        return payload


class BrowserTestDsu:
    def __init__(self) -> None:
        self.running = False
        self.controller = {
            "id": "path:browser-test-controller",
            "instance_id": 7,
            "name": "Manette de test",
            "type": "ps5",
            "type_id": 4,
            "vendor_id": 1356,
            "product_id": 3302,
            "path": "browser-test-controller",
            "gyro": True,
            "accelerometer": True,
            "compatible": True,
            "kind": "gamepad",
        }

    def status(self) -> dict:
        if self.running:
            return {
                "state": "ready",
                "state_label": "Gyroscope Joy-Con prêt",
                "message": "Mouvements transmis à Ryujinx sur 127.0.0.1:26760.",
                "engine_name": "JoyConDSU.exe",
                "supported": True,
                "running": True,
                "client_count": 1,
                "protocol_ready": True,
                "controllers": [self.controller],
                "selected_source": self.controller,
                "diagnostic": {
                    "status": "excellent",
                    "label": "Excellent",
                    "summary": "Signal régulier, récent et transmis sans anomalie notable.",
                },
                "telemetry": {
                    "clients": 1,
                    "received_hz": 199.8,
                    "sent_hz": 199.7,
                    "sample_age_ms": 3.2,
                    "received_jitter_mean_ms": 0.3,
                    "received_jitter_max_ms": 2.1,
                    "sent_jitter_mean_ms": 0.4,
                    "sent_jitter_max_ms": 2.4,
                    "duplicate_timestamps": 0,
                    "regressive_timestamps": 0,
                    "sent_packets": 1200,
                    "send_errors": 0,
                    "invalid_requests": 0,
                    "disconnects": 0,
                    "reconnects": 0,
                    "calibrations_valid": 1,
                    "calibrations_rejected": 0,
                },
            }
        return {
            "state": "stopped",
            "state_label": "Désactivé",
            "message": "Serveur local arrêté.",
            "engine_name": "JoyConDSU.exe",
            "supported": True,
            "running": False,
            "client_count": 0,
            "protocol_ready": False,
            "controllers": [self.controller],
            "selected_source": None,
            "diagnostic": {
                "status": "inactive",
                "label": "Diagnostic inactif",
                "summary": "Active le gyroscope pour mesurer la qualité du signal.",
            },
            "telemetry": None,
        }

    def start(self, _source_id=None) -> dict:
        self.running = True
        return self.status()

    def stop(self) -> dict:
        self.running = False
        return self.status()

    def close(self) -> None:
        self.running = False


class BrowserTestGuard:
    def acquire(self) -> bool:
        return True

    def close(self) -> None:
        pass


class BrowserTestNotifier:
    def close(self) -> None:
        pass


def build_report() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    report = analyze({})
    report["sauvegarde"] = {
        "slot": "1",
        "mode": "normal",
        "date": "2026-08-15 21:00:00",
        "chemin": "C:/Users/Test/AppData/Roaming/Ryujinx/bis/user/save/test/1",
        "plateforme": "Windows",
        "rubis": 120,
        "temps_jeu_secondes": 3600,
        "detection_mode": "slot 1 réservé au mode normal",
    }
    report["synchronisation"] = {
        "status": "a_jour",
        "status_label": "À jour",
        "last_success_at": now,
        "save_timestamp_at": now,
        "save_timestamp": 123456,
        "slot": "1",
        "save_mode": "normal",
        "source_kind": "standard",
        "source_root": "C:/Users/Test/AppData/Roaming/Ryujinx/bis/user/save/test",
        "report_revision": 1,
        "fingerprint": "browser-test-report",
        "events": [{"at": now, "kind": "succes", "message": "Sauvegarde de test chargée"}],
    }
    report["lune_de_sang"] = blood_moon_status({
        "FirstTouchdown": True,
        "WM_BloodyMoonTimer": 1008.0,
        "WM_Time": 215.0,
        "WM_BloodyDay": False,
    })
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18765)
    arguments = parser.parse_args()
    report = build_report()
    with tempfile.TemporaryDirectory(prefix="botw-companion-browser-") as directory:
        root = Path(directory)
        serve(
            lambda: report,
            port=arguments.port,
            open_browser=False,
            tracking_store=ManualTrackingStore(root / "manual_tracking.json"),
            route_store=RouteSessionStore(root / "route_sessions.json"),
            preference_store=PreferenceStore(root / "preferences.json"),
            runtime_state_store=RuntimeStateStore(root / "runtime_state.json"),
            sync_controller=BrowserTestSync(report),
            inactivity_seconds=3600,
            dsu_manager=BrowserTestDsu(),
            monitor_ryujinx=False,
            running_emulators_provider=lambda: [],
            instance_guard=BrowserTestGuard(),
            shutdown_notifier_factory=lambda _callback: BrowserTestNotifier(),
        )


if __name__ == "__main__":
    main()
