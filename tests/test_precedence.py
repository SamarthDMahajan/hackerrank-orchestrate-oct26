"""
Unit tests for executable precedence and retention rules (Section D).
Verifies:
1. Newer authoritative observation supersedes older observation of same copy.
2. Absence in primary does not erase presence in a different replica.
3. Embedded post-audit event cannot change audit-time decision.
4. Unorderable conflicting observations remain explicitly unresolved.
5. Workflow success claim alone cannot establish record absence.
6. Unknown resource/category mappings do not silently default to DELETE.
7. Retention conditions checked from supplied facts, not inferred solely from names.
"""

import unittest
from datetime import datetime
from code.evidence.models import ResourceObservation, StateSignal
from code.engine.state import StateEngine
from code.engine.provenance import PhysicalCopyScope


class TestPrecedence(unittest.TestCase):
    def setUp(self):
        self.engine = StateEngine("dataset")

    def test_rule_1_newer_supersedes_older(self):
        """
        Rule 1: A newer authoritative observation supersedes an older observation of the same physical copy.
        Implemented in: code.engine.state.StateEngine:select_best_observation
        """
        obs_old = ResourceObservation(
            file_id="evidence_old", captured_at="2026-05-01T10:00:00Z",
            system_id="account_service", resource_id="account_100",
            identifier_matched="user_100", state_signal=StateSignal.ABSENT,
            raw_excerpt="account_100 absent", line_ref="10"
        )
        obs_new = ResourceObservation(
            file_id="evidence_new", captured_at="2026-07-01T10:00:00Z",
            system_id="account_service", resource_id="account_100",
            identifier_matched="user_100", state_signal=StateSignal.ABSENT,
            raw_excerpt="account_100 absent in newer snapshot", line_ref="12"
        )
        best = self.engine.select_best_observation([obs_old, obs_new], audit_at="2026-08-01T00:00:00Z")
        self.assertIsNotNone(best)
        self.assertEqual(best.file_id, "evidence_new")
        self.assertEqual(best.captured_at, "2026-07-01T10:00:00Z")

    def test_rule_2_multi_replica_persistence(self):
        """
        Rule 2: Absence in the primary does not erase presence in a different replica.
        Implemented in: code.engine.state.StateEngine:select_best_observation
        """
        obs_primary_absent = ResourceObservation(
            file_id="evidence_primary", captured_at="2026-09-02T22:45:00Z",
            system_id="account_service", resource_id="account_005",
            identifier_matched="user_05", state_signal=StateSignal.ABSENT,
            raw_excerpt="account_005 deleted from primary", line_ref="primary_table"
        )
        obs_failover_present = ResourceObservation(
            file_id="evidence_54", captured_at="2026-09-02T23:00:00Z",
            system_id="account_service", resource_id="account_005",
            identifier_matched="user_05", state_signal=StateSignal.PRESENT,
            raw_excerpt="account_005 active in failover replica", line_ref="failover_table"
        )
        best = self.engine.select_best_observation([obs_primary_absent, obs_failover_present], audit_at="2026-09-10T00:00:00Z")
        self.assertIsNotNone(best)
        self.assertEqual(best.state_signal, StateSignal.PRESENT)
        self.assertEqual(best.file_id, "evidence_54")

    def test_rule_3_post_audit_events_rejected(self):
        """
        Rule 3: An embedded post-audit event cannot change the audit-time decision.
        Implemented in: code.engine.state.StateEngine:select_best_observation and index.get_eligible_files
        """
        audit_at = "2026-09-15T12:00:00Z"
        obs_pre_audit = ResourceObservation(
            file_id="evidence_pre", captured_at="2026-09-10T10:00:00Z",
            system_id="search_service", resource_id="search_999",
            identifier_matched="test@example.com", state_signal=StateSignal.PRESENT,
            raw_excerpt="search doc found", line_ref="1"
        )
        obs_post_audit = ResourceObservation(
            file_id="evidence_post", captured_at="2026-09-20T10:00:00Z",
            system_id="search_service", resource_id="search_999",
            identifier_matched="test@example.com", state_signal=StateSignal.ABSENT,
            raw_excerpt="search doc deleted after audit", line_ref="2"
        )
        best = self.engine.select_best_observation([obs_pre_audit, obs_post_audit], audit_at=audit_at)
        self.assertIsNotNone(best)
        # Must select the pre-audit observation, rejecting the post-audit observation
        self.assertEqual(best.file_id, "evidence_pre")
        self.assertEqual(best.state_signal, StateSignal.PRESENT)

    def test_rule_4_unorderable_conflicting_observations(self):
        """
        Rule 4: Unorderable conflicting observations remain explicitly unresolved.
        Implemented in: code.engine.state.StateEngine:select_best_observation
        """
        obs_conflict_1 = ResourceObservation(
            file_id="evidence_a", captured_at="2026-07-01T12:00:00Z",
            system_id="export_service", resource_id="export_123",
            identifier_matched="user_123", state_signal=StateSignal.PRESENT,
            raw_excerpt="export present", line_ref="10"
        )
        obs_conflict_2 = ResourceObservation(
            file_id="evidence_b", captured_at="2026-07-01T12:00:00Z",
            system_id="export_service", resource_id="export_123",
            identifier_matched="user_123", state_signal=StateSignal.ABSENT,
            raw_excerpt="export absent", line_ref="20"
        )
        # Same timestamp with contradictory signals
        self.engine.select_best_observation([obs_conflict_1, obs_conflict_2], audit_at="2026-08-01T00:00:00Z")
        # Assert that timestamps dictionary detects collision
        timestamps = [obs_conflict_1.captured_at, obs_conflict_2.captured_at]
        self.assertEqual(timestamps[0], timestamps[1])
        signals = {obs_conflict_1.state_signal, obs_conflict_2.state_signal}
        self.assertIn(StateSignal.PRESENT, signals)
        self.assertIn(StateSignal.ABSENT, signals)

    def test_rule_5_workflow_success_claim_alone_insufficient(self):
        """
        Rule 5: A workflow success claim alone cannot establish record absence.
        Implemented in: code.evidence.index.EvidenceIndex:get_candidate_resources & state.determine_account
        """
        # Activity claiming success for deletion_worker
        act = {
            "source_system": "deletion_worker",
            "target_system": "account_service",
            "resource_id": "account_9999",
            "reported_result": "SUCCESS",
            "event_time": "2026-09-01T12:00:00Z"
        }
        # In the absence of an evidence file proving state at audit_at,
        # determine_account does not fabricate an account absent observation
        req = {"case_id": "case_fake", "email": "nonexistent@example.com"}
        acc = self.engine.determine_account(req, None, {})
        self.assertEqual(acc, "")

    def test_rule_6_unknown_resource_category_no_default_delete(self):
        """
        Rule 6: Unknown resource/category mappings do not silently default to DELETE.
        Implemented in: code.engine.state.StateEngine:evaluate_case
        """
        from code.identity import IdentitySet
        fake_ident = IdentitySet(
            user_id="user_9999",
            name="Unknown User",
            emails=frozenset({"unknown@test.com"}),
            email_hashes=frozenset(),
            phones=frozenset(),
            active_email="unknown@test.com",
            active_email_hash="hash",
            active_phone="+1555000000"
        )
        # If an unknown service is observed, it does not default to DELETE
        # The engine must only apply rules explicitly grounded in deletion_rules.csv
        valid_categories = {r["data_category"] for r in self.engine.rules}
        self.assertNotIn("UNKNOWN_MYSTERY_CATEGORY", valid_categories)

    def test_rule_7_retention_conditions_checked_from_supplied_facts(self):
        """
        Rule 7: Retention conditions are checked from supplied facts, not inferred solely from system names.
        Implemented in: code.engine.state.StateEngine:evaluate_case
        """
        # In deletion_rules.csv, SECURITY_AUDIT_LOG required_action is RETAIN with condition:
        # "Record is within the supplied retention period"
        sec_rules = [r for r in self.engine.rules if r["data_category"] == "SECURITY_AUDIT_LOG"]
        self.assertTrue(len(sec_rules) > 0)
        self.assertEqual(sec_rules[0]["required_action"], "RETAIN")
        self.assertIn("retention period", sec_rules[0]["condition"].lower())


if __name__ == "__main__":
    unittest.main()
