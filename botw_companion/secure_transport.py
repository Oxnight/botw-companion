"""TLS transport shared by update discovery and installer downloads."""

from __future__ import annotations

import socket
import ssl
from pathlib import Path
from urllib.error import URLError
from urllib.request import HTTPSHandler, Request, build_opener, urlopen

try:
    import certifi
except ImportError:  # Source checkouts may be inspected before dependencies are installed.
    certifi = None


class CertificateBundleError(RuntimeError):
    """The packaged Mozilla trust store is missing or unusable."""


def certificate_bundle() -> Path:
    if certifi is None:
        raise CertificateBundleError("Le magasin de certificats HTTPS n'est pas installé")
    path = Path(certifi.where()).resolve()
    if not path.is_file() or path.stat().st_size < 100_000:
        raise CertificateBundleError("Le magasin de certificats HTTPS est absent ou incomplet")
    return path


def secure_ssl_context() -> ssl.SSLContext:
    """Return a verified TLS context with system and packaged trust stores."""
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=str(certificate_bundle()))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def secure_urlopen(request: Request, *, timeout: float):
    return urlopen(request, timeout=timeout, context=secure_ssl_context())


def secure_redirect_opener(redirect_handler, request: Request, *, timeout: float):
    opener = build_opener(
        redirect_handler,
        HTTPSHandler(context=secure_ssl_context()),
    )
    return opener.open(request, timeout=timeout)


def network_failure_reason(error: BaseException) -> str:
    """Classify an HTTPS failure without exposing sensitive exception text."""
    reason = getattr(error, "reason", error)
    if isinstance(reason, ssl.SSLCertVerificationError):
        return "tls"
    if isinstance(reason, ssl.SSLError):
        return "tls"
    if isinstance(reason, socket.gaierror):
        return "dns"
    if isinstance(error, (TimeoutError, socket.timeout)) or isinstance(
        reason, (TimeoutError, socket.timeout)
    ):
        return "timeout"
    if isinstance(error, CertificateBundleError) or isinstance(reason, CertificateBundleError):
        return "tls"
    if isinstance(error, (URLError, OSError)):
        return "network"
    return "network"


def certificate_bundle_errors() -> list[str]:
    try:
        secure_ssl_context()
    except (CertificateBundleError, OSError, ssl.SSLError) as exc:
        return [f"Transport HTTPS indisponible : {exc}"]
    return []
