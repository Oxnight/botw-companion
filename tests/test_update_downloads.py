import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time
from types import SimpleNamespace
import unittest
from urllib.error import HTTPError, URLError

from botw_companion.update_downloads import DownloadTarget, UpdateDownloadManager


class FakeHeaders(dict):
    def get(self, key, default=None):
        wanted = key.casefold()
        for name, value in self.items():
            if name.casefold() == wanted:
                return value
        return default


class FakeResponse:
    def __init__(self, payload, *, status=200, headers=None,
                 url="https://release-assets.githubusercontent.com/release.bin"):
        self.payload = payload
        self.status = status
        self.headers = FakeHeaders(headers or {})
        self.url = url
        self.offset = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def read(self, size=-1):
        if size < 0:
            size = len(self.payload) - self.offset
        chunk = self.payload[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk

    def geturl(self):
        return self.url


class FakeChecker:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def check(self, *, force=False):
        self.calls += 1
        return dict(self.payload)


def candidate(content: bytes, version="0.40.0-alpha." + "39") -> dict:
    filename = f"BOTW_Companion_{version}_Setup.exe"
    return {
        "status": "update_available",
        "update_available": True,
        "current_version": "0.40.0-alpha." + "38",
        "latest_version": version,
        "filename": filename,
        "download_url": (
            "https://github.com/Oxnight/botw-companion/releases/download/"
            f"v{version}/{filename}"
        ),
        "release_url": f"https://github.com/Oxnight/botw-companion/releases/tag/v{version}",
        "size": len(content),
        "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
        "content_type": "application/octet-stream",
    }


class UpdateDownloadManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def wait(manager, expected, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = manager.status()
            if state["status"] in expected:
                return state
            time.sleep(0.01)
        raise AssertionError(f"download remained in {manager.status()}")

    def manager(self, content, opener, **kwargs):
        checker = FakeChecker(candidate(content))
        manager = UpdateDownloadManager(
            checker,
            data_root=self.root,
            opener=opener,
            sleeper=lambda _seconds: None,
            random_value=lambda: 0,
            **kwargs,
        )
        return manager, checker

    def test_complete_download_is_verified_and_atomically_published(self):
        content = b"verified installer" * 1024
        calls = []

        def opener(request, timeout):
            calls.append((dict(request.header_items()), timeout))
            return FakeResponse(content, headers={"Content-Length": str(len(content)), "ETag": '"v1"'})

        manager, checker = self.manager(content, opener)
        manager.start()
        state = self.wait(manager, {"ready_to_install", "failed"})
        self.assertEqual(state["status"], "ready_to_install")
        self.assertEqual((self.root / candidate(content)["filename"]).read_bytes(), content)
        self.assertFalse(any("sum" in path.name.casefold() for path in self.root.iterdir()))
        self.assertEqual(checker.calls, 1)
        self.assertEqual(len(calls), 1)
        install = manager.installation_candidate()
        self.assertEqual(install.version, "0.40.0-alpha." + "39")
        self.assertEqual(install.installer.read_bytes(), content)
        self.assertEqual(install.digest, hashlib.sha256(content).hexdigest())

    def test_installation_candidate_rehashes_the_ready_file(self):
        content = b"verified before handoff"
        manager, _checker = self.manager(
            content,
            lambda *_args, **_kwargs: FakeResponse(
                content, headers={"Content-Length": str(len(content))}
            ),
        )
        manager.start()
        self.assertEqual(self.wait(manager, {"ready_to_install"})["status"], "ready_to_install")
        (self.root / candidate(content)["filename"]).write_bytes(b"tampered after download")
        with self.assertRaisesRegex(Exception, "sécurité"):
            manager.installation_candidate()

    def test_valid_partial_file_resumes_with_range_and_if_range(self):
        content = b"resume this transfer safely"
        payload = candidate(content)
        target = DownloadTarget.from_check(payload)
        part = self.root / f"{target.filename}.part"
        metadata = self.root / f"{target.filename}.metadata.json"
        part.write_bytes(content[:7])
        metadata.write_text(json.dumps(target.metadata(etag='"v1"')), encoding="utf-8")
        seen = {}

        def opener(request, timeout):
            seen.update(dict(request.header_items()))
            return FakeResponse(
                content[7:], status=206,
                headers={
                    "Content-Length": str(len(content) - 7),
                    "Content-Range": f"bytes 7-{len(content)-1}/{len(content)}",
                    "ETag": '"v1"',
                },
            )

        manager, _checker = self.manager(content, opener)
        manager.start()
        self.assertEqual(self.wait(manager, {"ready_to_install", "failed"})["status"], "ready_to_install")
        self.assertEqual(seen["Range"], "bytes=7-")
        self.assertEqual(seen["If-range"], '"v1"')

    def test_server_ignoring_range_restarts_from_zero(self):
        content = b"new complete representation"
        target = DownloadTarget.from_check(candidate(content))
        (self.root / f"{target.filename}.part").write_bytes(b"obsolete")
        (self.root / f"{target.filename}.metadata.json").write_text(
            json.dumps(target.metadata(etag='"old"')), encoding="utf-8"
        )

        manager, _checker = self.manager(
            content,
            lambda *_args, **_kwargs: FakeResponse(
                content, headers={"Content-Length": str(len(content)), "ETag": '"new"'}
            ),
        )
        manager.start()
        self.assertEqual(self.wait(manager, {"ready_to_install", "failed"})["status"], "ready_to_install")
        self.assertEqual((self.root / target.filename).read_bytes(), content)

    def test_interrupted_download_keeps_partial_bytes_for_retry(self):
        content = b"network data" * 100

        class BrokenResponse(FakeResponse):
            def read(self, size=-1):
                if self.offset:
                    raise OSError("connection lost")
                return super().read(25)

        manager, _checker = self.manager(
            content,
            lambda *_args, **_kwargs: BrokenResponse(
                content, headers={"Content-Length": str(len(content)), "ETag": '"v1"'}
            ),
            max_attempts=1,
        )
        manager.start()
        state = self.wait(manager, {"interrupted", "failed"})
        self.assertEqual(state["status"], "interrupted")
        self.assertEqual(next(self.root.glob("*.part")).stat().st_size, 25)
        self.assertTrue(state["can_retry"])

    def test_bad_digest_is_deleted_and_never_becomes_ready(self):
        content = b"expected package"
        wrong = b"tampered package"
        payload = candidate(wrong)
        payload["digest"] = "sha256:" + hashlib.sha256(content).hexdigest()
        checker = FakeChecker(payload)
        manager = UpdateDownloadManager(
            checker, data_root=self.root,
            opener=lambda *_args, **_kwargs: FakeResponse(
                wrong, headers={"Content-Length": str(len(wrong))}
            ),
            sleeper=lambda _seconds: None,
        )
        manager.start()
        state = self.wait(manager, {"failed"})
        self.assertIn("sécurité", state["message"])
        self.assertFalse(any(path.suffix in {".exe", ".part"} for path in self.root.iterdir()))

    def test_untrusted_redirect_destination_is_rejected(self):
        content = b"package"
        manager, _checker = self.manager(
            content,
            lambda *_args, **_kwargs: FakeResponse(
                content,
                headers={"Content-Length": str(len(content))},
                url="https://evil.example/package.exe",
            ),
            max_attempts=1,
        )
        manager.start()
        state = self.wait(manager, {"failed", "interrupted"})
        self.assertEqual(state["status"], "failed")
        self.assertIn("Destination", state["message"])

    def test_disk_shortage_stops_before_network_access(self):
        content = b"large enough package"
        calls = []
        usage = SimpleNamespace(total=100, used=99, free=1)
        manager, _checker = self.manager(
            content,
            lambda *_args, **_kwargs: calls.append(True),
            disk_usage=lambda _path: usage,
            max_attempts=1,
        )
        manager.start()
        state = self.wait(manager, {"failed"})
        self.assertIn("Espace disque", state["message"])
        self.assertEqual(calls, [])

    def test_offline_check_is_retryable_and_does_not_touch_existing_data(self):
        personal = self.root / "personal.json"
        personal.write_text("keep", encoding="utf-8")
        manager = UpdateDownloadManager(
            FakeChecker({"status": "unavailable", "update_available": False}),
            data_root=self.root / "updates",
        )
        manager.start()
        state = self.wait(manager, {"interrupted"})
        self.assertTrue(state["can_retry"])
        self.assertEqual(personal.read_text(encoding="utf-8"), "keep")

    def test_double_start_uses_one_worker(self):
        content = b"single worker"
        entered = []

        def opener(*_args, **_kwargs):
            entered.append(True)
            return FakeResponse(content, headers={"Content-Length": str(len(content))})

        manager, checker = self.manager(content, opener)
        manager.start()
        manager.start()
        self.wait(manager, {"ready_to_install", "failed"})
        self.assertEqual(checker.calls, 1)
        self.assertEqual(len(entered), 1)

    def test_cancel_preserves_downloaded_fragment(self):
        content = b"cancel safely" * 100
        holder = {}

        class CancellingResponse(FakeResponse):
            def read(self, size=-1):
                chunk = super().read(32)
                if chunk:
                    holder["manager"].cancel()
                return chunk

        manager, _checker = self.manager(
            content,
            lambda *_args, **_kwargs: CancellingResponse(
                content, headers={"Content-Length": str(len(content)), "ETag": '"v1"'}
            ),
        )
        holder["manager"] = manager
        manager.start()
        state = self.wait(manager, {"cancelled", "failed"})
        self.assertEqual(state["status"], "cancelled")
        self.assertGreater(next(self.root.glob("*.part")).stat().st_size, 0)

    def test_verified_file_survives_restart_without_network(self):
        content = b"already verified"
        first, _checker = self.manager(
            content,
            lambda *_args, **_kwargs: FakeResponse(
                content, headers={"Content-Length": str(len(content))}
            ),
        )
        first.start()
        self.assertEqual(self.wait(first, {"ready_to_install", "failed"})["status"], "ready_to_install")
        calls = []
        second, _checker = self.manager(
            content,
            lambda *_args, **_kwargs: calls.append(True),
        )
        second.start()
        self.assertEqual(self.wait(second, {"ready_to_install", "failed"})["status"], "ready_to_install")
        self.assertEqual(calls, [])

    def test_partial_file_for_another_release_is_discarded(self):
        content = b"current package"
        target = DownloadTarget.from_check(candidate(content))
        part = self.root / f"{target.filename}.part"
        metadata = self.root / f"{target.filename}.metadata.json"
        part.write_bytes(b"stale")
        stale = target.metadata(etag='"old"')
        stale["digest"] = "sha256:" + "0" * 64
        metadata.write_text(json.dumps(stale), encoding="utf-8")
        manager, _checker = self.manager(
            content,
            lambda *_args, **_kwargs: FakeResponse(
                content, headers={"Content-Length": str(len(content))}
            ),
        )
        manager.start()
        self.assertEqual(self.wait(manager, {"ready_to_install", "failed"})["status"], "ready_to_install")
        self.assertEqual((self.root / target.filename).read_bytes(), content)

    def test_unsatisfiable_range_discards_fragment_and_restarts(self):
        content = b"replacement package"
        target = DownloadTarget.from_check(candidate(content))
        (self.root / f"{target.filename}.part").write_bytes(content[:4])
        (self.root / f"{target.filename}.metadata.json").write_text(
            json.dumps(target.metadata(etag='"old"')), encoding="utf-8"
        )
        calls = []

        def opener(request, timeout):
            calls.append(dict(request.header_items()))
            if len(calls) == 1:
                raise HTTPError(request.full_url, 416, "range", {}, None)
            return FakeResponse(content, headers={"Content-Length": str(len(content))})

        manager, _checker = self.manager(content, opener)
        manager.start()
        self.assertEqual(self.wait(manager, {"ready_to_install", "failed"})["status"], "ready_to_install")
        self.assertIn("Range", calls[0])
        self.assertNotIn("Range", calls[1])

    def test_wrong_length_and_excess_bytes_are_rejected(self):
        content = b"expected bytes"
        responses = (
            FakeResponse(content, headers={"Content-Length": str(len(content) + 1)}),
            FakeResponse(content + b"extra"),
        )
        for response in responses:
            with self.subTest(response=response):
                case_root = self.root / str(id(response))
                manager = UpdateDownloadManager(
                    FakeChecker(candidate(content)),
                    data_root=case_root,
                    opener=lambda *_args, current=response, **_kwargs: current,
                    max_attempts=1,
                    sleeper=lambda _seconds: None,
                )
                manager.start()
                self.assertEqual(self.wait(manager, {"failed", "interrupted"})["status"], "failed")
                self.assertFalse((case_root / candidate(content)["filename"]).exists())


if __name__ == "__main__":
    unittest.main()
