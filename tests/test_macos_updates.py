import hashlib
import plistlib
from pathlib import Path
import tempfile
import unittest

from botw_companion.macos_updates import (
    INSTALL_STATE_NAME,
    MacOSUpdateError,
    MacOSUpdateInstaller,
)
from botw_companion.update_downloads import UpdateInstallCandidate


class FakeProcess:
    def poll(self):
        return None


class MacOSUpdateTests(unittest.TestCase):
    VERSION = "0.40.0-alpha." + "40"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / "updates"
        self.application = self.base / "Applications" / "BOTW Companion.app"
        self.executable = self.application / "Contents" / "MacOS" / "BOTW Companion"
        self.executable.parent.mkdir(parents=True)
        self.executable.write_bytes(b"arm64 app")
        self.helper = self.base / "macos_update_relay.sh"
        self.helper.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
        self.dmg = self.root / f"BOTW_Companion_{self.VERSION}_macOS_arm64.dmg"
        self.dmg.parent.mkdir(parents=True)
        self.dmg.write_bytes(b"verified dmg")
        self.digest = hashlib.sha256(self.dmg.read_bytes()).hexdigest()
        self.metadata = self.root / f"{self.dmg.name}.metadata.json"
        self.metadata.write_text(
            "{" +
            f'"ready": true, "version": "{self.VERSION}", '
            f'"filename": "{self.dmg.name}", "size": {self.dmg.stat().st_size}, '
            f'"digest": "sha256:{self.digest}"' +
            "}",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def candidate(self):
        return UpdateInstallCandidate(
            version=self.VERSION,
            installer=self.dmg,
            size=self.dmg.stat().st_size,
            digest=self.digest,
            metadata=self.metadata,
            release_url=f"https://github.com/Oxnight/botw-companion/releases/tag/v{self.VERSION}",
        )

    def installer(self, **values):
        return MacOSUpdateInstaller(
            data_root=self.root,
            application=self.executable,
            helper=self.helper,
            system=values.pop("system", "Darwin"),
            machine=values.pop("machine", "arm64"),
            frozen=values.pop("frozen", True),
            owner_uid=values.pop("owner_uid", 501),
            owner_gid=values.pop("owner_gid", 20),
            **values,
        )

    def test_coordinator_launches_a_detached_argument_list(self):
        calls = []

        def popen(command, **kwargs):
            calls.append((command, kwargs))
            return FakeProcess()

        state = self.installer(popen=popen).start(
            self.candidate(), parent_pid=4321, port=8765
        )
        self.assertEqual(state["status"], "scheduled")
        command, options = calls[0]
        self.assertEqual(command[0], "/bin/bash")
        self.assertIn("--bundle-version", command)
        self.assertIn("40.0.40", command)
        self.assertIn("--parent-pid", command)
        self.assertIn("4321", command)
        self.assertIn("--owner-uid", command)
        self.assertIn("501", command)
        self.assertIn("--owner-gid", command)
        self.assertIn("20", command)
        self.assertTrue(options["start_new_session"])
        self.assertTrue(options["close_fds"])
        self.assertFalse(options.get("shell", False))
        relay = Path(command[1])
        self.assertTrue(relay.is_file())
        self.assertEqual(relay.stat().st_mode & 0o777, 0o700)

    def test_only_a_frozen_apple_silicon_bundle_is_supported(self):
        self.assertTrue(self.installer().supported())
        self.assertFalse(self.installer(machine="x86_64").supported())
        self.assertFalse(self.installer(system="Windows").supported())
        self.assertFalse(self.installer(frozen=False).supported())

    def test_tampering_after_download_blocks_the_relay(self):
        self.dmg.write_bytes(b"tampered")
        with self.assertRaisesRegex(MacOSUpdateError, "sécurité"):
            self.installer().start(self.candidate(), parent_pid=1, port=8765)

    def test_candidate_metadata_must_still_be_ready_and_exact(self):
        self.metadata.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(MacOSUpdateError, "sécurité"):
            self.installer().start(self.candidate(), parent_pid=1, port=8765)

    def test_status_exposes_only_public_plist_fields(self):
        with (self.root / INSTALL_STATE_NAME).open("wb") as stream:
            plistlib.dump({
                "status": "failed",
                "version": self.VERSION,
                "message": "échec contrôlé",
                "can_retry": True,
                "secret": "never expose",
            }, stream)
        state = self.installer().status()
        self.assertEqual(state["status"], "failed")
        self.assertNotIn("secret", state)

    def test_relay_script_contains_transactional_safety_checks(self):
        relay = (Path(__file__).resolve().parents[1] / "botw_companion" /
                 "macos_update_relay.sh").read_text(encoding="utf-8")
        for required in (
            "hdiutil verify", "-readonly", "-nobrowse", "codesign --verify --deep --strict",
            "CFBundleIdentifier", "CFBundleShortVersionString", "CFBundleVersion",
            "lipo -archs", "shasum -a 256", "/usr/bin/ditto", "administratorPrivileges",
            "rollback_performed", "Application.currentApplication", "launchctl asuser",
        ):
            self.assertIn(required, relay)
        self.assertNotIn("xattr -d", relay)
        self.assertNotIn("spctl --master-disable", relay)


if __name__ == "__main__":
    unittest.main()
