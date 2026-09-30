import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from botw_companion.versioning import CURRENT_VERSION
from tools.verify_release_assets import ReleaseAssetError, verify_release_assets
from tools.verify_release_ref import ReleaseRefError, verify_release_ref


class ReleaseSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]

    def test_every_action_is_pinned_and_publication_is_least_privilege(self):
        workflow = (self.root / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        action_refs = re.findall(r"^\s*uses:\s*([^@\s]+)@([^\s#]+)", workflow, re.MULTILINE)
        self.assertGreaterEqual(len(action_refs), 8)
        for action, reference in action_refs:
            with self.subTest(action=action):
                self.assertRegex(reference, r"^[0-9a-f]{40}$")
        self.assertIn("permissions:\n  contents: read", workflow)
        publish = workflow.split("  publish:\n", 1)[1]
        self.assertIn("permissions:\n      contents: write", publish)
        self.assertIn("name: github-release", publish)
        self.assertEqual(workflow.count("persist-credentials: false"), 3)
        self.assertEqual(workflow.count("fetch-depth: 0"), 3)

    def test_release_remains_a_draft_until_exact_assets_are_verified(self):
        workflow = (self.root / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        draft = workflow.index("Create the draft GitHub release")
        verify = workflow.index("Verify GitHub's uploaded assets")
        publish = workflow.index("Publish the verified release")
        final = workflow.index("Verify the published release")
        cleanup = workflow.index("Remove an unverified release")
        self.assertLess(draft, verify)
        self.assertLess(verify, publish)
        self.assertLess(publish, final)
        self.assertLess(final, cleanup)
        self.assertIn("--draft", workflow[draft:verify])
        self.assertIn("tools/verify_release_assets.py", workflow[verify:publish])
        self.assertIn("tools/verify_release_ref.py", workflow)
        self.assertIn("steps.create_release.outputs.created == 'true'", workflow)
        self.assertIn("gh api --method DELETE", workflow[cleanup:])
        self.assertIn("steps.create_release.outputs.release_id", workflow)
        self.assertIn("tools/release_lookup.py", workflow)
        self.assertNotIn("releases/tags/", workflow[verify:])
        self.assertNotIn("--cleanup-tag", workflow[cleanup:])
        self.assertNotIn("SHA256" + "SUMS", workflow)

    def test_annotated_tag_must_point_at_the_checked_out_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "config", "user.email", "ci@example.invalid"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "config", "user.name", "Release Test"],
                check=True,
            )
            (root / "source.txt").write_text("release\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "source.txt"], check=True)
            subprocess.run(
                ["git", "-C", str(root), "commit", "-q", "-m", "release"],
                check=True,
            )
            commit = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            subprocess.run(
                [
                    "git", "-C", str(root), "tag", "-a", CURRENT_VERSION.tag,
                    "-m", CURRENT_VERSION.title,
                ],
                check=True,
            )
            verify_release_ref(root, CURRENT_VERSION.tag, commit)
            tag_object = subprocess.run(
                ["git", "-C", str(root), "rev-parse", f"refs/tags/{CURRENT_VERSION.tag}"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            verify_release_ref(root, CURRENT_VERSION.tag, tag_object)
            with self.assertRaisesRegex(ReleaseRefError, "cannot be resolved"):
                verify_release_ref(root, CURRENT_VERSION.tag, "0" * 40)
            subprocess.run(
                ["git", "-C", str(root), "tag", "-d", CURRENT_VERSION.tag],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "tag", CURRENT_VERSION.tag], check=True
            )
            with self.assertRaisesRegex(ReleaseRefError, "annotated"):
                verify_release_ref(root, CURRENT_VERSION.tag, commit)

    def _release_fixture(self, directory: Path) -> tuple[dict, Path]:
        assets = directory / "assets"
        assets.mkdir(parents=True)
        payload = {
            "tag_name": CURRENT_VERSION.tag,
            "name": CURRENT_VERSION.title,
            "draft": True,
            "prerelease": CURRENT_VERSION.is_prerelease,
            "assets": [],
        }
        for name, content_type in (
            (CURRENT_VERSION.installer_name, "application/x-msdownload"),
            (CURRENT_VERSION.dmg_name, "application/x-apple-diskimage"),
        ):
            path = assets / name
            path.write_bytes((name + "\n").encode("utf-8"))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            payload["assets"].append({
                "name": name,
                "state": "uploaded",
                "size": path.stat().st_size,
                "digest": f"sha256:{digest}",
                "content_type": content_type,
                "browser_download_url": (
                    "https://github.com/Oxnight/botw-companion/releases/download/"
                    f"{CURRENT_VERSION.tag}/{name}"
                ),
            })
        return payload, assets

    def test_release_asset_verifier_rejects_substitution_and_extra_files(self):
        with tempfile.TemporaryDirectory() as directory:
            payload, assets = self._release_fixture(Path(directory))
            verify_release_assets(
                payload, assets, "Oxnight/botw-companion", published=False
            )
            payload["draft"] = False
            verify_release_assets(
                payload, assets, "Oxnight/botw-companion", published=True
            )
            payload["assets"][0]["digest"] = "sha256:" + "0" * 64
            with self.assertRaisesRegex(ReleaseAssetError, "digest differs"):
                verify_release_assets(
                    payload, assets, "Oxnight/botw-companion", published=True
                )
            payload, assets = self._release_fixture(Path(directory) / "second")
            payload["assets"].append(json.loads(json.dumps(payload["assets"][0])))
            payload["assets"][-1]["name"] = "unexpected.txt"
            with self.assertRaisesRegex(ReleaseAssetError, "exactly two"):
                verify_release_assets(
                    payload, assets, "Oxnight/botw-companion", published=False
                )


if __name__ == "__main__":
    unittest.main()
