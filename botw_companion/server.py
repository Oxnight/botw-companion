from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from hmac import compare_digest
from importlib.resources import files
from socketserver import TCPServer
import gzip
import json
import re
import secrets
import signal
import sys
import threading
from urllib.parse import parse_qs, unquote, urlsplit
import webbrowser

from .backup import CompanionBackup
from .manual_tracking import ManualTrackingError, ManualTrackingStore
from .dsu import DsuManager
from .lifecycle import APPLICATION_NAME, EmulatorLifecycleWatcher, WebLifecycle
from .emulators import any_supported_emulator_running, running_emulators
from .platforms import (
    platform_metadata,
    ryujinx_is_running,
    server_instance_guard,
    system_shutdown_notifier,
)
from .route_sessions import RouteSessionStore
from .preferences import PreferenceStore
from .runtime_state import RuntimeStateStore
from .report_views import ReportViewCache, report_revision_key
from .save_caption import SaveCaptionError, read_selected_caption
from .synchronization import ReliableSaveSync
from .updates import UpdateChecker
from . import __version__


SESSION_HEADER = "X-BOTW-Session-Token"
SESSION_PLACEHOLDER = "__BOTW_SESSION_TOKEN__"
CONTENT_SECURITY_POLICY = "; ".join((
    "default-src 'self'",
    "base-uri 'none'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    "form-action 'none'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "connect-src 'self'",
    "font-src 'self'",
    "media-src 'none'",
    "worker-src 'none'",
    "manifest-src 'self'",
))


class RequestPayloadError(ManualTrackingError):
    """Deterministic HTTP error raised before domain validation."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


class LoopbackThreadingHTTPServer(ThreadingHTTPServer):
    """Local server that avoids reverse DNS lookup while opening the socket."""

    def server_bind(self) -> None:
        # HTTPServer.server_bind() calls socket.getfqdn() after binding. That
        # lookup is unnecessary for a server restricted to 127.0.0.1 and can
        # hang on some macOS runners. TCPServer performs the same bind without
        # DNS access; retain the public HTTPServer attributes.
        TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)


def serve(payload_factory, port: int = 8765, open_browser: bool = True,
          tracking_store: ManualTrackingStore | None = None,
          route_store: RouteSessionStore | None = None,
          preference_store: PreferenceStore | None = None,
          runtime_state_store: RuntimeStateStore | None = None,
          sync_controller: ReliableSaveSync | None = None,
          inactivity_seconds: float = 300,
          dsu_manager: DsuManager | None = None,
          monitor_ryujinx: bool = False,
          ryujinx_running=None,
          monitor_emulator: bool = False,
          emulator_running=None,
          running_emulators_provider=None,
          instance_guard=None,
          shutdown_notifier_factory=None,
          server_ready=None,
          session_token: str | None = None,
          update_checker: UpdateChecker | None = None) -> None:
    web_root = files("botw_companion.web")
    tracking_store = tracking_store or ManualTrackingStore()
    route_store = route_store or RouteSessionStore()
    preference_store = preference_store or PreferenceStore()
    runtime_state_store = runtime_state_store or RuntimeStateStore()
    backup_manager = CompanionBackup(tracking_store, route_store, preference_store)
    report_views = ReportViewCache()
    lifecycle = WebLifecycle(inactivity_seconds)
    dsu_manager = dsu_manager or DsuManager()
    update_checker = update_checker or UpdateChecker()
    session_token = session_token or secrets.token_urlsafe(32)
    if not isinstance(session_token, str) or not session_token:
        raise ValueError("Le jeton de session local ne peut pas être vide")
    if running_emulators_provider is None:
        running_emulators_provider = running_emulators

    def remember_sync(synchronization: object) -> None:
        try:
            runtime_state_store.update_sync(synchronization)
        except (ManualTrackingError, OSError):
            pass

    def current_report(force: bool = False) -> dict:
        report = sync_controller.report(force=force) if sync_controller else payload_factory()
        if sync_controller and isinstance(report.get("synchronisation"), dict):
            remember_sync(report["synchronisation"])
        return report

    class Handler(BaseHTTPRequestHandler):
        def end_headers(self) -> None:
            self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header(
                "Permissions-Policy",
                "accelerometer=(), camera=(), geolocation=(), microphone=(), payment=()",
            )
            self.send_header("X-Permitted-Cross-Domain-Policies", "none")
            super().end_headers()

        def _json_response(self, status: int, payload: object, **headers: str) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            compressed = len(body) >= 1024 and "gzip" in self.headers.get("Accept-Encoding", "").lower()
            if compressed:
                body = gzip.compress(body, compresslevel=5)
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            if compressed:
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Vary", "Accept-Encoding")
            self.send_header("Content-Length", str(len(body)))
            for name, value in headers.items():
                self.send_header(name.replace("_", "-"), value)
            self.end_headers()
            self.wfile.write(body)

        def _reject_request(self, status: int, message: str) -> bool:
            self._json_response(status, {"erreur": message})
            return False

        def _request_is_allowed(self, *, mutating: bool = False) -> bool:
            expected_authority = f"127.0.0.1:{self.server.server_port}"
            hosts = self.headers.get_all("Host", [])
            if len(hosts) != 1 or hosts[0].strip().casefold() != expected_authority:
                return self._reject_request(421, "Hôte local invalide")

            origins = self.headers.get_all("Origin", [])
            expected_origin = f"http://{expected_authority}"
            if len(origins) > 1 or (origins and origins[0].strip() != expected_origin):
                return self._reject_request(403, "Origine non autorisée")

            fetch_sites = self.headers.get_all("Sec-Fetch-Site", [])
            if len(fetch_sites) > 1 or (
                fetch_sites and fetch_sites[0].strip().casefold() not in {"same-origin", "none"}
            ):
                return self._reject_request(403, "Contexte de navigation non autorisé")

            if mutating:
                supplied_token = self.headers.get(SESSION_HEADER, "")
                if not compare_digest(supplied_token, session_token):
                    return self._reject_request(403, "Jeton de session local invalide")
            return True

        @staticmethod
        def _payload_error_status(exc: ManualTrackingError) -> int:
            if isinstance(exc, RequestPayloadError):
                return exc.status
            return 409 if "autre fenêtre" in str(exc) else 400

        def _read_json(self) -> object:
            if self.headers.get("Transfer-Encoding"):
                raise RequestPayloadError("Encodage de transfert non accepté")
            content_types = self.headers.get_all("Content-Type", [])
            media_type = (
                content_types[0].split(";", 1)[0].strip().casefold()
                if len(content_types) == 1 else ""
            )
            if media_type != "application/json":
                raise RequestPayloadError("Content-Type application/json requis", 415)
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1:
                raise RequestPayloadError("Taille de requête invalide")
            try:
                length = int(lengths[0])
            except ValueError as exc:
                raise RequestPayloadError("Taille de requête invalide") from exc
            if length <= 0 or length > 2_000_000:
                status = 413 if length > 2_000_000 else 400
                raise RequestPayloadError("Requête vide ou trop volumineuse", status)
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RequestPayloadError("JSON invalide") from exc

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlsplit(self.path)
            path = parsed.path
            force = parse_qs(parsed.query).get("force", ["0"])[0] == "1"
            if not self._request_is_allowed(mutating=force):
                return
            if path == "/api/report":
                try:
                    payload = report_views.bootstrap(current_report(force))
                except Exception as exc:
                    self._json_response(500, {"erreur": str(exc)})
                else:
                    self._json_response(200, payload)
                return
            if path == "/api/catalog":
                try:
                    payload = report_views.catalog(current_report(False))
                except Exception as exc:
                    self._json_response(500, {"erreur": str(exc)})
                else:
                    self._json_response(200, payload)
                return
            if path == "/api/save-caption":
                try:
                    caption = read_selected_caption(current_report(False))
                except (SaveCaptionError, OSError) as exc:
                    self._json_response(404, {"erreur": str(exc)})
                else:
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("ETag", f'"{caption.etag}"')
                    self.send_header("Content-Length", str(len(caption.data)))
                    self.end_headers()
                    self.wfile.write(caption.data)
                return
            if path.startswith("/api/detail/"):
                try:
                    full_report = current_report(False)
                    item = report_views.detail(full_report, unquote(path.removeprefix("/api/detail/")))
                    payload = ({"schema_version": 1, "report_revision_key": report_revision_key(full_report),
                                "item": item} if item is not None else None)
                except Exception as exc:
                    self._json_response(500, {"erreur": str(exc)})
                else:
                    self._json_response(200, payload) if payload is not None else self._json_response(404, {"erreur": "Objectif introuvable"})
                return
            if path == "/api/sync" and sync_controller:
                try:
                    payload = sync_controller.check(force=force)
                    remember_sync(payload.get("synchronisation", {}))
                except Exception as exc:
                    self._json_response(500, {"erreur": str(exc)})
                else:
                    self._json_response(200, payload)
                return
            if path == "/api/dsu":
                self._json_response(200, dsu_manager.status())
                return
            if path == "/api/version":
                self._json_response(200, {
                    "application": APPLICATION_NAME,
                    "api_schema_version": 1,
                    "version": __version__,
                    "session_token": session_token,
                    "platform": platform_metadata(),
                    "emulators": {
                        "supported": ["Ryujinx", "Cemu"],
                        "running": [backend.label for backend in running_emulators_provider()],
                    },
                    "lifecycle": {
                        "monitoring_emulator": bool(monitor_emulator or monitor_ryujinx),
                        "monitoring_ryujinx": monitor_ryujinx,
                        "shutdown_reason": lifecycle.shutdown_reason,
                    },
                })
                return
            if path == "/api/update":
                self._json_response(200, update_checker.check(force=force))
                return
            if path in {"/api/manual", "/api/manual/export"}:
                try:
                    payload = tracking_store.load()
                    headers = ({"Content_Disposition": "attachment; filename=botw-companion-suivi-manuel.json"}
                               if path.endswith("/export") else {})
                except ManualTrackingError as exc:
                    self._json_response(500, {"erreur": str(exc)})
                else:
                    self._json_response(200, payload, **headers)
                return
            if path in {"/api/routes", "/api/routes/export"}:
                try:
                    payload = route_store.load()
                    headers = ({"Content_Disposition": "attachment; filename=botw-companion-itineraires.json"}
                               if path.endswith("/export") else {})
                except ManualTrackingError as exc:
                    self._json_response(500, {"erreur": str(exc)})
                else:
                    self._json_response(200, payload, **headers)
                return
            if path == "/api/preferences":
                try:
                    payload = preference_store.load()
                except ManualTrackingError as exc:
                    self._json_response(500, {"erreur": str(exc)})
                else:
                    self._json_response(200, payload)
                return
            if path == "/api/backup/export":
                try:
                    payload = backup_manager.export()
                except ManualTrackingError as exc:
                    self._json_response(500, {"erreur": str(exc)})
                else:
                    self._json_response(200, payload, Content_Disposition="attachment; filename=botw-companion-sauvegarde.json")
                return
            name = path.lstrip("/") or "index.html"
            tile_request = re.fullmatch(r"map-tiles/z[1-3]/\d+_\d+\.webp", name)
            if name not in {"index.html", "app.js", "route_planner.js", "style.css", "metrics.css", "armor.css", "hyrule-map.webp"} and not tile_request:
                self.send_error(404)
                return
            content = web_root.joinpath(*name.split("/")).read_bytes()
            if name == "index.html":
                content = content.replace(
                    SESSION_PLACEHOLDER.encode(), session_token.encode()
                )
            mime = {"html": "text/html", "js": "text/javascript", "css": "text/css",
                    "webp": "image/webp"}[name.rsplit(".", 1)[1]]
            self.send_response(200)
            self.send_header("Content-Type", f"{mime}; charset=utf-8")
            if name == "index.html":
                self.send_header("Cache-Control", "no-store")
            elif tile_request:
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_PUT(self) -> None:  # noqa: N802
            if not self._request_is_allowed(mutating=True):
                return
            path = urlsplit(self.path).path
            if path == "/api/preferences":
                try:
                    data = self._read_json()
                    if not isinstance(data, dict) or "values" not in data:
                        raise ManualTrackingError("Préférences invalides")
                    result = preference_store.update(
                        data["values"], data.get("expected_revision")
                    )
                    self._json_response(200, result)
                except ManualTrackingError as exc:
                    self._json_response(self._payload_error_status(exc), {"erreur": str(exc)})
                return
            if path == "/api/routes":
                try:
                    data = self._read_json()
                    if not isinstance(data, dict) or "routes" not in data:
                        raise ManualTrackingError("État des itinéraires invalide")
                    result = route_store.replace(data["routes"], data.get("expected_revision"))
                    self._json_response(200, result)
                except ManualTrackingError as exc:
                    self._json_response(self._payload_error_status(exc), {"erreur": str(exc)})
                return
            if not path.startswith("/api/manual/") or path == "/api/manual/import":
                self.send_error(404)
                return
            try:
                data = self._read_json()
                if not isinstance(data, dict):
                    raise ManualTrackingError("État de suivi invalide")
                result = tracking_store.update(
                    unquote(path.removeprefix("/api/manual/")),
                    data.get("completed"), data.get("note", ""), data.get("expected_revision"),
                )
                self._json_response(200, result)
            except ManualTrackingError as exc:
                self._json_response(self._payload_error_status(exc), {"erreur": str(exc)})

        def do_POST(self) -> None:  # noqa: N802
            if not self._request_is_allowed(mutating=True):
                return
            path = urlsplit(self.path).path
            if path == "/api/heartbeat":
                self._json_response(200, lifecycle.heartbeat())
                return
            if path == "/api/shutdown":
                dsu_manager.stop()
                self._json_response(200, {"status": "arret", "message": "BOTW Companion va s’arrêter"})
                request_server_shutdown("bouton_quitter")
                return
            if path == "/api/dsu/start":
                source_id = None
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = 0
                if length > 0:
                    try:
                        data = self._read_json()
                        if isinstance(data, dict):
                            source_id = data.get("source_id")
                    except ManualTrackingError as exc:
                        self._json_response(self._payload_error_status(exc), {"erreur": str(exc)})
                        return
                payload = dsu_manager.start(source_id) if source_id else dsu_manager.start()
                self._json_response(
                    200 if payload["state"] not in {"error", "unavailable"} else 503,
                    payload,
                )
                return
            if path == "/api/dsu/stop":
                self._json_response(200, dsu_manager.stop())
                return
            if path == "/api/routes/import":
                try:
                    data = self._read_json()
                    if not isinstance(data, dict) or "session" not in data:
                        raise ManualTrackingError("Fichier d’import d’itinéraire invalide")
                    result = route_store.import_session(data["session"], data.get("expected_revision"))
                    self._json_response(200, result)
                except ManualTrackingError as exc:
                    self._json_response(self._payload_error_status(exc), {"erreur": str(exc)})
                return
            if path == "/api/backup/import":
                try:
                    data = self._read_json()
                    if not isinstance(data, dict) or "backup" not in data:
                        raise ManualTrackingError("Sauvegarde générale invalide")
                    result = backup_manager.restore(data["backup"])
                    self._json_response(200, result)
                except (ManualTrackingError, OSError) as exc:
                    self._json_response(self._payload_error_status(exc), {"erreur": str(exc)})
                return
            if path != "/api/manual/import":
                self.send_error(404)
                return
            try:
                data = self._read_json()
                if not isinstance(data, dict) or "tracking" not in data:
                    raise ManualTrackingError("Fichier d’import invalide")
                result = tracking_store.import_data(
                    data["tracking"], data.get("mode", "merge"), data.get("expected_revision"),
                )
                self._json_response(200, result)
            except ManualTrackingError as exc:
                self._json_response(self._payload_error_status(exc), {"erreur": str(exc)})

        def do_OPTIONS(self) -> None:  # noqa: N802
            # No CORS API: a remote page must never be allowed to query the
            # loopback server.
            self._reject_request(403, "Requête inter-origine non autorisée")

        def log_message(self, _format: str, *_args) -> None:
            pass

    guard = instance_guard or server_instance_guard()
    if not guard.acquire():
        raise OSError("Une instance de BOTW Companion fonctionne déjà pour cet utilisateur")
    try:
        server = LoopbackThreadingHTTPServer(("127.0.0.1", port), Handler)
    except Exception:
        guard.close()
        raise
    lifecycle_stop = threading.Event()

    def request_server_shutdown(reason: str) -> None:
        if lifecycle.should_shutdown():
            return
        lifecycle.request_shutdown(reason)
        threading.Thread(
            target=server.shutdown,
            name="botw-companion-shutdown",
            daemon=True,
        ).start()

    shutdown_notifier = (
        shutdown_notifier_factory(request_server_shutdown)
        if shutdown_notifier_factory is not None
        else system_shutdown_notifier(request_server_shutdown)
    )

    def monitor_lifecycle() -> None:
        while not lifecycle_stop.wait(15):
            if lifecycle.should_shutdown():
                server.shutdown()
                return

    threading.Thread(target=monitor_lifecycle, name="botw-companion-lifecycle", daemon=True).start()
    watcher = None
    if monitor_emulator or monitor_ryujinx:
        detector = emulator_running or (ryujinx_running if monitor_ryujinx and not monitor_emulator else None)
        watcher = EmulatorLifecycleWatcher(
            detector or any_supported_emulator_running,
            request_server_shutdown,
        )
        watcher.start()

    previous_signals = {}

    def handle_signal(signum, _frame) -> None:
        request_server_shutdown(f"signal_{signum}")

    if threading.current_thread() is threading.main_thread():
        for signal_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
            signum = getattr(signal, signal_name, None)
            if signum is not None:
                previous_signals[signum] = signal.getsignal(signum)
                signal.signal(signum, handle_signal)
    bound_port = int(server.server_address[1])
    url = f"http://127.0.0.1:{bound_port}"
    browser_url = f"{url}/#session={session_token}"
    if server_ready is not None:
        server_ready(bound_port)
    if sys.stdout is not None:
        print(f"Interface BOTW Companion : {url}")
        print("Laisse ce terminal ouvert. Ctrl+C pour arrêter.")
    if open_browser:
        threading.Timer(0.35, lambda: webbrowser.open(browser_url)).start()
    try:
        server.serve_forever()
    finally:
        lifecycle_stop.set()
        if watcher is not None:
            watcher.stop()
        dsu_manager.close()
        server.server_close()
        shutdown_notifier.close()
        guard.close()
        for signum, previous in previous_signals.items():
            signal.signal(signum, previous)
