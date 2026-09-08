from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.audit_distribution import PUBLIC_DOCUMENTS, audit, documentation_errors


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
                "lien cassé dans README.md : docs/ABSENT.md",
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
                "# Document\n[Dépannage](docs/TROUBLESHOOTING.md#section-absente)\n",
                encoding="utf-8",
            )
            self.assertIn(
                "ancre cassée dans README.md : docs/TROUBLESHOOTING.md#section-absente",
                documentation_errors(root),
            )


if __name__ == "__main__":
    unittest.main()
