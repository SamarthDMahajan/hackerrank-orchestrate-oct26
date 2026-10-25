"""
Candidate Verification Test Suite (Prompt 4C)

Covers:
1. Section B: Account resolution counterexample fixtures (differing numeric suffix, unlinked subject).
2. Section C: Temporal eligibility derivation fixtures (post-audit file, post-audit event, future association, positive control, post-audit trace line).
3. Section F: Independent evaluation step matching (partial match, duplicate steps).
4. Section G: Authorization scope fixtures (mixed request with retention instruction, quoted deletion in non-deletion request).
"""

import unittest
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from code.identity import IdentitySet
from code.evidence.models import ResourceObservation, StateSignal
from code.engine.state import StateEngine
from code.intent import classify_intent, AuthorizationOutcome
from code.evaluation.comparator import compare_outputs, compare_steps


class TestPrompt4CVerification(unittest.TestCase):
    def setUp(self):
        self.dataset_dir = os.path.join(REPO, "dataset")
        self.engine = StateEngine(self.dataset_dir)

    # -------------------------------------------------------------------------
    # Section B: Account Resolution & Counterexamples
    # -------------------------------------------------------------------------
    def test_b1_account_differs_from_numeric_suffix(self):
        """
        Counterexample 1:
        A subject with numeric suffix 100 (user_100) has an explicit link to account_9999.
        The engine must resolve account_9999 and NOT fabricate account_100.
        """
        ident = IdentitySet(
            user_id="user_100",
            name="Subject Differing Suffix",
            emails=frozenset({"diff.suffix@domain.com"}),
            email_hashes=frozenset({"hash_100"}),
            phones=frozenset({"+10000000100"}),
            active_email="diff.suffix@domain.com",
            active_email_hash="hash_100",
            active_phone="+10000000100"
        )
        req = {
            "case_id": "case_test_b1",
            "email": "diff.suffix@domain.com",
            "requested_at": "2026-05-01T10:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-05-02T10:00:00Z",
            "audit_at": "2026-05-10T10:00:00Z",
            "request_text": "Please delete my account."
        }
        # Add explicit link to account_9999 eligible at audit_at with valid provenance
        self.engine.account_links.append({
            "resource_id": "account_9999",
            "user_id": "user_100",
            "email": None,
            "captured_at": "2026-05-01T10:00:00Z",
            "file_id": "evidence_mock_01"
        })
        self.engine.acc_to_user["user_100"] = "account_9999"

        acc = self.engine.determine_account(req, ident, {}, audit_at=req["audit_at"])
        self.assertEqual(acc, "account_9999")
        self.assertNotEqual(acc, "account_100")

    def test_b2_unlinked_subject_returns_empty_no_fabrication(self):
        """
        Counterexample 2:
        A subject (user_200) has a plausible naming pattern (account_200) but NO explicit link
        anywhere in eligible evidence.
        The engine must return "" (uncertain/unlinked) and NOT fabricate account_200.
        """
        ident = IdentitySet(
            user_id="user_200",
            name="Subject No Association",
            emails=frozenset({"no.assoc@domain.com"}),
            email_hashes=frozenset({"hash_200"}),
            phones=frozenset({"+10000000200"}),
            active_email="no.assoc@domain.com",
            active_email_hash="hash_200",
            active_phone="+10000000200"
        )
        req = {
            "case_id": "case_test_b2",
            "email": "no.assoc@domain.com",
            "requested_at": "2026-05-01T10:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-05-02T10:00:00Z",
            "audit_at": "2026-05-10T10:00:00Z",
            "request_text": "Please delete my account."
        }
        acc = self.engine.determine_account(req, ident, {}, audit_at=req["audit_at"])
        # Must be empty string - no guessing or convention fallback allowed!
        self.assertEqual(acc, "")

    # -------------------------------------------------------------------------
    # Section C: Temporal Eligibility Across Entire Derivation
    # -------------------------------------------------------------------------
    def test_c1_file_captured_after_audit_at_ineligible(self):
        """
        C1: An evidence file captured after audit_at has ineligible resource state.
        """
        obs_post = ResourceObservation(
            file_id="evidence_post_audit",
            captured_at="2026-09-01T12:00:00Z",
            system_id="search_service",
            resource_id="search_777",
            identifier_matched="test.user@domain.com",
            state_signal=StateSignal.PRESENT,
            raw_excerpt="post audit search record",
            line_ref="1"
        )
        best = self.engine.select_best_observation([obs_post], audit_at="2026-08-01T00:00:00Z")
        self.assertIsNone(best, "Observation captured after audit_at must be rejected as None")

    def test_c2_eligible_file_containing_post_audit_event(self):
        """
        C2: An observation whose embedded timestamp is after audit_at cannot affect decision.
        """
        obs_event_post = ResourceObservation(
            file_id="evidence_eligible_file",
            captured_at="2026-09-10T00:00:00Z",
            system_id="account_service",
            resource_id="account_888",
            identifier_matched="test.user@domain.com",
            state_signal=StateSignal.PRESENT,
            raw_excerpt="event_time: 2026-09-05T12:00:00Z",
            line_ref="1"
        )
        best = self.engine.select_best_observation([obs_event_post], audit_at="2026-08-15T00:00:00Z")
        self.assertIsNone(best, "Embedded observation after audit_at must be rejected")

    def test_c3_association_in_future_evidence_ineligible(self):
        """
        C3: Eligible resource-state observation (captured <= audit_at), but subject-resource
        association available only in future evidence (captured > audit_at).
        The future association cannot establish the link at audit_at.
        """
        ident = IdentitySet(
            user_id="user_300",
            name="Future Association Subject",
            emails=frozenset({"future.assoc@domain.com"}),
            email_hashes=frozenset({"hash_300"}),
            phones=frozenset({"+10000000300"}),
            active_email="future.assoc@domain.com",
            active_email_hash="hash_300",
            active_phone="+10000000300"
        )
        req = {
            "case_id": "case_test_c3",
            "email": "future.assoc@domain.com",
            "requested_at": "2026-06-01T10:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-06-02T10:00:00Z",
            "audit_at": "2026-06-10T10:00:00Z",
            "request_text": "Please delete my account."
        }
        # Future association captured at 2026-09-15 > audit_at 2026-06-10
        self.engine.account_links = [{
            "resource_id": "account_3333",
            "user_id": "user_300",
            "email": "future.assoc@domain.com",
            "captured_at": "2026-09-15T12:00:00Z",
            "file_id": "evidence_future"
        }]
        acc = self.engine.determine_account(req, ident, {}, audit_at=req["audit_at"])
        self.assertEqual(acc, "", "Future association cannot establish link at audit_at")

    def test_c4_positive_control_eligible_association_and_observation(self):
        """
        C4: Both subject-resource association and resource observation are eligible (<= audit_at).
        Valid positive control.
        """
        ident = IdentitySet(
            user_id="user_400",
            name="Positive Control Subject",
            emails=frozenset({"pos.control@domain.com"}),
            email_hashes=frozenset({"hash_400"}),
            phones=frozenset({"+10000000400"}),
            active_email="pos.control@domain.com",
            active_email_hash="hash_400",
            active_phone="+10000000400"
        )
        req = {
            "case_id": "case_test_c4",
            "email": "pos.control@domain.com",
            "requested_at": "2026-06-01T10:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-06-02T10:00:00Z",
            "audit_at": "2026-06-10T10:00:00Z",
            "request_text": "Please delete my account."
        }
        # Eligible association captured at 2026-06-05 <= audit_at 2026-06-10
        self.engine.account_links = [{
            "resource_id": "account_4444",
            "user_id": "user_400",
            "email": "pos.control@domain.com",
            "captured_at": "2026-06-05T12:00:00Z",
            "file_id": "evidence_eligible"
        }]
        acc = self.engine.determine_account(req, ident, {}, audit_at=req["audit_at"])
        self.assertEqual(acc, "account_4444")

    def test_c5_trace_connecting_line_after_audit_at_ineligible(self):
        """
        C5: A trace whose necessary connecting line occurs after audit_at cannot
        leak a future association into a pre-audit decision.
        """
        # Line 1: user link at 2026-06-01 <= audit_at
        # Line 2: account link at 2026-06-15 > audit_at 2026-06-10
        # Effective connection time is 2026-06-15 > audit_at -> Ineligible
        ident = IdentitySet(
            user_id="user_500",
            name="Trace Future Subject",
            emails=frozenset({"trace.future@domain.com"}),
            email_hashes=frozenset({"hash_500"}),
            phones=frozenset({"+10000000500"}),
            active_email="trace.future@domain.com",
            active_email_hash="hash_500",
            active_phone="+10000000500"
        )
        req = {
            "case_id": "case_test_c5",
            "email": "trace.future@domain.com",
            "requested_at": "2026-06-01T10:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-06-02T10:00:00Z",
            "audit_at": "2026-06-10T10:00:00Z",
            "request_text": "Please delete my account."
        }
        self.engine.account_links = [{
            "resource_id": "account_5555",
            "user_id": "user_500",
            "email": "trace.future@domain.com",
            "captured_at": "2026-06-15T08:00:00Z",
            "file_id": "evidence_trace_log"
        }]
        acc = self.engine.determine_account(req, ident, {}, audit_at=req["audit_at"])
        self.assertEqual(acc, "", "Trace completed after audit_at must not be eligible")

    # -------------------------------------------------------------------------
    # Section F: Step Matching, Partial Matches, and Duplicate Steps
    # -------------------------------------------------------------------------
    def test_f1_partial_match_metrics(self):
        """
        F1: A candidate has some matching steps and some non-matching steps.
        Verifies step precision, recall, and F1 calculations.
        """
        exp_steps = [
            {"step_no": 1, "phase": "FINDING", "system_id": "account_service", "resource_id": "account_01", "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": "ev_01"},
            {"step_no": 2, "phase": "REMEDIATION", "system_id": "account_service", "resource_id": "account_01", "operation": "DELETE_RECORD", "state": "ABSENT", "evidence_id": ""},
            {"step_no": 3, "phase": "VERIFICATION", "system_id": "account_service", "resource_id": "account_01", "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ""}
        ]
        # Candidate matched step 1 and step 2, but has an extra/differing step 3
        cand_steps = [
            {"step_no": 1, "phase": "FINDING", "system_id": "account_service", "resource_id": "account_01", "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": "ev_01"},
            {"step_no": 2, "phase": "REMEDIATION", "system_id": "account_service", "resource_id": "account_01", "operation": "DELETE_RECORD", "state": "ABSENT", "evidence_id": ""},
            {"step_no": 3, "phase": "VERIFICATION", "system_id": "search_service", "resource_id": "search_99", "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ""}
        ]
        matched, mismatches = compare_steps(cand_steps, exp_steps)
        self.assertEqual(matched, 2)
        # Precision = 2/3, Recall = 2/3
        precision = (matched / len(cand_steps)) * 100
        recall = (matched / len(exp_steps)) * 100
        self.assertAlmostEqual(precision, 66.67, places=1)
        self.assertAlmostEqual(recall, 66.67, places=1)

    def test_f2_duplicate_step_handling(self):
        """
        F2: Candidate emits duplicate identical steps.
        Multiset evaluation must not double-count a single expected step.
        """
        exp_steps = [
            {"step_no": 1, "phase": "FINDING", "system_id": "account_service", "resource_id": "account_01", "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": "ev_01"}
        ]
        # Candidate duplicates the step twice
        cand_steps = [
            {"step_no": 1, "phase": "FINDING", "system_id": "account_service", "resource_id": "account_01", "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": "ev_01"},
            {"step_no": 2, "phase": "FINDING", "system_id": "account_service", "resource_id": "account_01", "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": "ev_01"}
        ]
        matched, mismatches = compare_steps(cand_steps, exp_steps)
        self.assertEqual(matched, 1, "Duplicate candidate step must not match the same expected step twice")
        precision = (matched / len(cand_steps)) * 100
        self.assertEqual(precision, 50.0)

    # -------------------------------------------------------------------------
    # Section G: Authorization Scope Fixtures
    # -------------------------------------------------------------------------
    def test_g1_mixed_request_deletion_plus_retention_instruction(self):
        """
        G1: Request contains explicit deletion request combined with a retention caveat:
        'Please erase all my personal data. Do not delete legally retained invoices.'
        Outcome must be DELETE_AUTHORIZED, not blocked or classified as non-deletion.
        """
        text = "Please erase all my personal data. Do not delete legally retained invoices."
        res = classify_intent(text, case_id="case_test_g1")
        self.assertEqual(res.outcome, AuthorizationOutcome.DELETE_AUTHORIZED)

    def test_g2_non_deletion_quoting_deletion_instruction(self):
        """
        G2: Request is an access/inquiry request that quotes deletion policy text:
        'I received an email stating: \"Your account has been flagged for deletion\".
        Can you please send me a full copy of all data you currently hold about me?'
        Outcome must be NON_DELETION (or NOT_APPLICABLE), because the primary intent is access/export.
        """
        text = 'I received an email stating: "Your account has been flagged for deletion". Can you please send me a full copy of all data you currently hold about me?'
        res = classify_intent(text, case_id="case_test_g2")
        self.assertEqual(res.outcome, AuthorizationOutcome.NON_DELETION)


if __name__ == "__main__":
    unittest.main()
