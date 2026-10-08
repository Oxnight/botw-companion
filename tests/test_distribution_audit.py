from pathlib import Path
from tempfile import TemporaryDirectory
import ast
import unittest

from tools.audit_distribution import (
    PUBLIC_DOCUMENTS,
    REQUIRED_RELEASE_SOURCES,
    audit,
    documentation_errors,
    public_language_errors,
    repository_hygiene_errors,
    release_source_errors,
    source_comment_language_errors,
)


class DistributionAuditTests(unittest.TestCase):
    def test_release_source_audit_rejects_missing_browser_script(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in REQUIRED_RELEASE_SOURCES:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("source\n", encoding="utf-8")
            self.assertEqual(release_source_errors(root), [])
            (root / "tools/browser_smoke.js").unlink()
            self.assertIn("missing or empty release source: tools/browser_smoke.js",
                          release_source_errors(root))

    def test_release_source_audit_rejects_missing_package_tests(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertIn("missing or empty release source: tests/test_windows_package.py",
                          release_source_errors(root))

    def test_distribution_metadata_is_complete(self):
        self.assertEqual(audit(), [])

    def test_documentation_audit_rejects_a_broken_relative_link(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in PUBLIC_DOCUMENTS:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# Document\n", encoding="utf-8")
            (root / "README.md").write_text(
                "# Document\n[Guide absent](docs/ABSENT.md)\n",
                encoding="utf-8",
            )
            self.assertIn(
                "broken link in README.md: docs/ABSENT.md",
                documentation_errors(root),
            )

    def test_documentation_audit_rejects_a_broken_anchor(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in PUBLIC_DOCUMENTS:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# Document\n", encoding="utf-8")
            (root / "README.md").write_text(
                "# Document\n[Troubleshooting](docs/TROUBLESHOOTING.md#missing-section)\n",
                encoding="utf-8",
            )
            self.assertIn(
                "broken anchor in README.md: docs/TROUBLESHOOTING.md#missing-section",
                documentation_errors(root),
            )

    def test_public_language_audit_rejects_french_prose(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in PUBLIC_DOCUMENTS:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# Document\nEnglish prose.\n", encoding="utf-8")
            (root / "README.md").write_text(
                "# Document\nCette documentation est en français.\n",
                encoding="utf-8",
            )
            self.assertTrue(public_language_errors(root))

    def test_public_language_audit_allows_quoted_french_ui_labels(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in PUBLIC_DOCUMENTS:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# Document\nEnglish prose.\n", encoding="utf-8")
            (root / "README.md").write_text(
                "# Document\nSelect **Vérifier les mises à jour**.\n",
                encoding="utf-8",
            )
            self.assertEqual(public_language_errors(root), [])

    def test_repository_hygiene_rejects_generated_files_without_git(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            bad = root / "build" / "debug.log"
            bad.parent.mkdir()
            bad.write_text("diagnostic", encoding="utf-8")
            findings = repository_hygiene_errors(root)
            self.assertTrue(any("build/debug.log" in finding for finding in findings))

    def test_repository_hygiene_rejects_historical_documents(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in (
                "CHANGELOG.md", "RELEASE_NOTES.md", "docs/RC99_REVIEW.md",
                "docs/RELEASE_CANDIDATE_VALIDATION.md", "docs/CLEANUP_REPORT.md",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# Historical notes\n", encoding="utf-8")
            findings = repository_hygiene_errors(root)
            self.assertEqual(len(findings), 5)
            self.assertTrue(all("forbidden historical document" in item for item in findings))

    def test_repository_hygiene_allows_permanent_security_and_release_docs(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ("docs/UPDATE_SECURITY.md", "docs/RELEASE_PROCESS.md"):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("# Maintainer procedure\n", encoding="utf-8")
            self.assertEqual(repository_hygiene_errors(root), [])

    def test_release_descriptions_do_not_require_repository_history_files(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("CHANGELOG.md", "RELEASE_NOTES.md"):
            self.assertFalse((root / name).exists())
            for relative in (
                ".github/workflows/release.yml", "macos/BOTW Companion.spec",
                "tools/build_windows_app.ps1", "tools/build_macos_app.sh",
                "tools/test_windows_installation.ps1", "tools/test_macos_installation.sh",
                "tools/check_version_consistency.py",
            ):
                with self.subTest(file=relative, history=name):
                    self.assertNotIn(name, (root / relative).read_text(encoding="utf-8"))

    def test_map_rebuild_preserves_the_current_provenance_notice(self):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / "tools/build_map_tiles.py").read_text(encoding="utf-8"))
        notice = next(
            ast.literal_eval(node.value) for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "SOURCE_NOTICE"
                    for target in node.targets)
        )
        self.assertEqual(notice, (root / "botw_companion/web/map-tiles/SOURCE.txt").read_text(
            encoding="utf-8"
        ))
        self.assertIn("no written redistribution", notice)

    def test_source_language_audit_rejects_french_comments_and_docstrings(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "example.py"
            source.write_text(
                '"""Cette fonction lit une sauvegarde."""\n'
                "# Vérifier les données avant le retour.\n",
                encoding="utf-8",
            )
            findings = source_comment_language_errors(root)
            self.assertTrue(any("docstring" in finding for finding in findings))
            self.assertTrue(any("comment" in finding for finding in findings))


if __name__ == "__main__":
    unittest.main()
