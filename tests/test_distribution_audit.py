import unittest

from tools.audit_distribution import audit


class DistributionAuditTests(unittest.TestCase):
    def test_distribution_metadata_is_complete(self):
        self.assertEqual(audit(), [])


if __name__ == "__main__":
    unittest.main()
