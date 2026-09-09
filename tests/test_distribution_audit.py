from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.audit_distribution import (
    PUBLIC_DOCUMENTS,
    audit,
    documentation_errors,
    public_language_errors,
    repository_hygiene_errors,
    source_comment_language_errors,
)


class DistributionAuditTests(unittest.TestCase):
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
