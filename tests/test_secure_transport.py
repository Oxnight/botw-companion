import socket
import ssl
import unittest
from urllib.error import URLError

from botw_companion.secure_transport import (
    certificate_bundle,
    network_failure_reason,
    secure_ssl_context,
)


class SecureTransportTests(unittest.TestCase):
    def test_certifi_bundle_and_verified_context_are_available(self):
        bundle = certificate_bundle()
        self.assertTrue(bundle.is_file())
        self.assertGreater(bundle.stat().st_size, 100_000)
        context = secure_ssl_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertGreaterEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)

    def test_failures_are_classified_without_exposing_exception_text(self):
        cases = (
            (URLError(ssl.SSLCertVerificationError("private detail")), "tls"),
            (URLError(socket.gaierror("private detail")), "dns"),
            (URLError(TimeoutError("private detail")), "timeout"),
            (URLError(OSError("private detail")), "network"),
        )
        for error, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(network_failure_reason(error), expected)


if __name__ == "__main__":
    unittest.main()
