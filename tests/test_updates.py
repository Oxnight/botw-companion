import json
import unittest
from urllib.error import URLError

from botw_companion.updates import MAX_RESPONSE_BYTES, RELEASES_API, UpdateChecker
from botw_companion.versioning import ReleaseVersion


class FakeResponse:
    def __init__(self, payload, status=200, url=RELEASES_API):
        self.payload = payload
        self.status = status
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def read(self, size=-1):
        return self.payload[:size] if size >= 0 else self.payload

    def geturl(self):
        return self.url


def release(version, *, prerelease=True, draft=False, asset_platform="windows"):
    parsed = ReleaseVersion.parse(version)
    filename = parsed.installer_name if asset_platform == "windows" else parsed.dmg_name
    tag = parsed.tag
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
        "html_url": f"https://github.com/Oxnight/botw-companion/releases/tag/{tag}",
        "assets": [{
            "name": filename,
            "state": "uploaded",
            "size": 123456,
            "digest": "sha256:" + "a" * 64,
            "content_type": "application/octet-stream",
            "browser_download_url":
                f"https://github.com/Oxnight/botw-companion/releases/download/{tag}/{filename}",
        }],
    }


class UpdateCheckerTests(unittest.TestCase):
    def checker(self, releases, **kwargs):
        calls = []

        def opener(request, timeout):
            calls.append((request.full_url, timeout))
            return FakeResponse(json.dumps(releases).encode())

        return UpdateChecker(opener=opener, timeout=0.25, **kwargs), calls

    def test_prerelease_selects_newest_release_and_exact_windows_asset(self):
        current = ReleaseVersion.parse("0.40.0-alpha.7")
        checker, calls = self.checker([
            release("0.40.0-alpha.8"),
            release("0.40.0-alpha.99", draft=True),
            release("0.40.0-alpha.6"),
        ], current=current, system="Windows")
        payload = checker.check()
        self.assertEqual(payload["latest_version"], "0.40.0-alpha.8")
        self.assertEqual(payload["filename"], "BOTW_Companion_0.40.0-alpha.8_Setup.exe")
        self.assertEqual(payload["digest"], "sha256:" + "a" * 64)
        self.assertEqual(payload["size"], 123456)
        self.assertEqual(calls, [(RELEASES_API, 0.25)])

    def test_stable_channel_ignores_prereleases(self):
        checker, _ = self.checker([
            release("1.1.0-alpha.1"),
            release("1.0.1", prerelease=False),
        ], current=ReleaseVersion.parse("1.0.0"), system="Windows")
        self.assertEqual(checker.check()["latest_version"], "1.0.1")

    def test_macos_requires_arm64_dmg(self):
        checker, _ = self.checker(
            [release("0.40.0-alpha.8", asset_platform="macos")],
            current=ReleaseVersion.parse("0.40.0-alpha.7"),
            system="Darwin",
        )
        self.assertTrue(checker.check()["filename"].endswith("_macOS_arm64.dmg"))

    def test_tampered_download_host_is_rejected(self):
        candidate = release("0.40.0-alpha.8")
        candidate["assets"][0]["browser_download_url"] = "https://evil.example/setup.exe"
        checker, _ = self.checker(
            [candidate], current=ReleaseVersion.parse("0.40.0-alpha.7"), system="Windows"
        )
        self.assertEqual(checker.check()["status"], "unavailable")

    def test_missing_digest_wrong_type_and_excessive_size_are_rejected(self):
        mutations = (
            lambda asset: asset.pop("digest"),
            lambda asset: asset.update(content_type="text/html"),
            lambda asset: asset.update(size=2_000_000_000),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                candidate = release("0.40.0-alpha.8")
                mutate(candidate["assets"][0])
                checker, _ = self.checker(
                    [candidate], current=ReleaseVersion.parse("0.40.0-alpha.7"), system="Windows"
                )
                self.assertEqual(checker.check()["status"], "unavailable")

    def test_api_redirect_is_rejected(self):
        checker = UpdateChecker(
            system="Windows",
            opener=lambda *_args, **_kwargs: FakeResponse(
                b"[]", url="https://evil.example/releases"
            ),
        )
        self.assertEqual(checker.check()["status"], "unavailable")

    def test_timeout_is_contained_cached_and_force_bypasses_cache(self):
        calls = []

        def failing(_request, timeout):
            calls.append(timeout)
            raise URLError("offline")

        checker = UpdateChecker(system="Windows", opener=failing, timeout=0.2)
        self.assertEqual(checker.check()["status"], "unavailable")
        self.assertEqual(checker.check()["status"], "unavailable")
        self.assertEqual(len(calls), 1)
        self.assertEqual(checker.check(force=True)["status"], "unavailable")
        self.assertEqual(len(calls), 2)

    def test_unsupported_platform_never_opens_network(self):
        checker = UpdateChecker(
            system="Linux",
            opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("aucun réseau attendu")
            ),
        )
        self.assertEqual(checker.check()["status"], "unsupported")

    def test_oversized_and_malformed_responses_are_contained(self):
        for payload in (b"{not-json", b"[" + b" " * MAX_RESPONSE_BYTES + b"]"):
            with self.subTest(size=len(payload)):
                checker = UpdateChecker(
                    system="Windows",
                    opener=lambda *_args, data=payload, **_kwargs: FakeResponse(data),
                )
                self.assertEqual(checker.check()["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
