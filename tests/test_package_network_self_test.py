import contextlib
import io
import ssl
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from botw_companion import macos_app, windows_app
from botw_companion.updates import RELEASES_API, UpdateChecker


class PackageNetworkSelfTestTests(unittest.TestCase):
    def run_probe(self, module, error):
        def opener(*args, **kwargs):
            raise error
        checker = UpdateChecker(
            system="Darwin" if module is macos_app else "Windows",
            opener=opener, max_attempts=1,
        )
        with patch.object(module, "UpdateChecker", return_value=checker), \
                contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            return module.package_network_self_test(), checker.check()

    def test_api_quota_response_passes_transport_probe_only(self):
        for module in (macos_app, windows_app):
            for code, headers in ((403, {"X-RateLimit-Remaining": "0"}),
                                  (403, {"Retry-After": "60"}), (429, {})):
                with self.subTest(platform=module.__name__, code=code, headers=headers):
                    result, update = self.run_probe(
                        module, HTTPError(RELEASES_API, code, "quota", headers, None)
                    )
                    self.assertEqual(result, 0)
                    self.assertEqual(update["status"], "unavailable")
                    self.assertEqual(update["reason"], "rate_limited")
                    self.assertFalse(update["update_available"])

    def test_real_transport_and_non_quota_http_errors_still_fail(self):
        errors = (
            URLError(ssl.SSLCertVerificationError("certificate failure")),
            URLError(OSError("offline")), TimeoutError("timeout"),
            HTTPError(RELEASES_API, 403, "forbidden", {}, None),
            HTTPError(RELEASES_API, 500, "server error", {}, None),
        )
        for module in (macos_app, windows_app):
            for error in errors:
                with self.subTest(platform=module.__name__, error=type(error).__name__):
                    result, update = self.run_probe(module, error)
                    self.assertEqual(result, 1)
                    self.assertEqual(update["status"], "unavailable")

    def test_normal_release_checks_still_pass(self):
        for module in (macos_app, windows_app):
            for status in ("up_to_date", "update_available"):
                with self.subTest(platform=module.__name__, status=status), \
                        patch.object(module, "UpdateChecker") as checker, \
                        contextlib.redirect_stdout(io.StringIO()):
                    checker.return_value.check.return_value = {"status": status}
                    self.assertEqual(module.package_network_self_test(), 0)
