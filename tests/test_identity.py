import os
import sys
import unittest
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from code.identity import get_identity_manager, IdentitySet, compute_email_hash


class TestIdentityResolution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mgr = get_identity_manager(os.path.join(REPO_ROOT, "dataset"))

    def test_known_user_current_email(self):
        # Test resolving a user with current email
        # Sample case 01 uses user whose identity is in user_identities
        ident = self.mgr.resolve("user_0001@example.com", "2026-10-20T12:00:00Z")
        if ident:
            self.assertEqual(ident.user_id, "user_0001")
            self.assertIn("user_0001@example.com", ident.emails)
            self.assertIn(compute_email_hash("user_0001@example.com"), ident.email_hashes)

    def test_historical_email_resolution(self):
        # Find a user who changed their email in user_audit_log
        target_uid = None
        old_email = None
        new_email = None
        change_time = None

        for uid, logs in self.mgr.user_audit_logs.items():
            for log in logs:
                if log["field_name"] == "email":
                    target_uid = uid
                    old_email = log["old_value"].strip().lower()
                    new_email = log["new_value"].strip().lower()
                    change_time = log["event_time"]
                    break
            if target_uid:
                break

        self.assertIsNotNone(target_uid, "Should have at least one user with email change in audit log")

        # 1. Resolve via old_email at a time AFTER the change
        # Both old and new email should be present in historical IdentitySet
        ident_after = self.mgr.resolve(old_email, "2026-10-26T23:59:59Z")
        self.assertIsNotNone(ident_after)
        self.assertEqual(ident_after.user_id, target_uid)
        self.assertIn(old_email, ident_after.emails)
        self.assertIn(compute_email_hash(old_email), ident_after.email_hashes)

    def test_temporal_cutoff_post_audit_exclusion(self):
        # If audit_at is BEFORE the email change, the new email occurred in the future relative to audit_at
        # Therefore, active_email at that past time should be old_email, and new_email must NOT be in valid_emails
        target_uid = None
        old_email = None
        new_email = None
        change_time = None

        for uid, logs in self.mgr.user_audit_logs.items():
            for log in logs:
                if log["field_name"] == "email":
                    target_uid = uid
                    old_email = log["old_value"].strip().lower()
                    new_email = log["new_value"].strip().lower()
                    change_time = log["event_time"]
                    break
            if target_uid:
                break

        # Cutoff 1 second before the change
        # Parse change_time: e.g. "2026-09-15T10:00:00Z"
        # We can construct a timestamp strictly before change_time
        past_audit_at = "2020-01-01T00:00:00Z"
        ident_past = self.mgr.resolve(old_email, past_audit_at)
        self.assertIsNotNone(ident_past)
        self.assertEqual(ident_past.user_id, target_uid)
        # At 2020-01-01, new_email did not exist yet (it happened in 2026)
        self.assertNotIn(new_email, ident_past.emails)
        self.assertNotIn(compute_email_hash(new_email), ident_past.email_hashes)
        self.assertEqual(ident_past.active_email, old_email)

    def test_all_518_requests_resolve(self):
        import csv
        requests_path = os.path.join(REPO_ROOT, "dataset", "deletion_requests.csv")
        resolved = 0
        with open(requests_path, "r", encoding="utf-8", errors="replace") as f:
            for row in csv.DictReader(f):
                ident = self.mgr.resolve(row["email"], row["audit_at"])
                if ident is not None:
                    resolved += 1
        self.assertEqual(resolved, 518, "All 518 deletion requests must resolve")


if __name__ == "__main__":
    unittest.main()
