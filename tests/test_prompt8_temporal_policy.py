"""
Production-path regression tests for Prompt 8:
Authoritative temporal semantics, strict evidence cutoffs,
metadata separation, policy retention grounding, and tombstone preservation.
HackerRank Orchestrate (October 2026) - Ghost Data Still Exists.
"""

import os
import unittest
import tempfile
import shutil
import csv
import json

from code.identity import IdentitySet, IdentityManager, compute_email_hash
from code.evidence.index import EvidenceIndex
from code.evidence.models import StateSignal, ResourceObservation
from code.evidence.image_parser import parse_visual_evidence
from code.contracts import (
    VerdictCertainty,
    PlanCompleteness,
    DeletionStatus,
    Phase,
    Step,
    CaseEvaluationResult,
)
from code.engine.state import StateEngine
from code.main import process_requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(REPO_ROOT, "dataset")


def make_test_ident(user_id: str, email: str, name: str = "Test User") -> IdentitySet:
    h = compute_email_hash(email)
    return IdentitySet(
        user_id=user_id,
        name=name,
        emails=frozenset([email]),
        email_hashes=frozenset([h]),
        phones=frozenset(),
        active_email=email,
        active_email_hash=h,
        active_phone=""
    )


class TestPrompt8TemporalPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = StateEngine(DATASET_DIR)
        cls.index = EvidenceIndex(DATASET_DIR)
        cls.id_mgr = IdentityManager(DATASET_DIR)

    def test_01_late_file_old_event_rejected(self):
        """
        1. Late file + old event rejected:
        A source captured after audit_at remains ineligible even when an embedded event is older.
        Specifically verifies that evidence_06 (captured 2026-09-18) is rejected for case_09 (audit_at 2026-09-16).
        """
        obs_late_file = ResourceObservation(
            file_id="evidence_late",
            captured_at="2026-09-20T12:00:00Z",  # Late file
            system_id="security_service",
            resource_id="audit_record_test",
            identifier_matched="user_test",
            state_signal=StateSignal.PRESENT,
            raw_excerpt="test",
            line_ref="test.log:1",
            observed_timestamp="2026-09-10T12:00:00Z"  # Older event
        )
        audit_at = "2026-09-15T12:00:00Z"
        best = self.engine.select_best_observation([obs_late_file], audit_at)
        self.assertIsNone(best, "Late file must be rejected even if embedded event is older")

        # Real case_09 check: evidence_06 was captured on 2026-09-18T11:55:24Z, after audit_at 2026-09-16
        with open(os.path.join(DATASET_DIR, "sample_deletion_requests.csv"), "r", encoding="utf-8") as f:
            reqs = {r["case_id"]: r for r in csv.DictReader(f)}
        req_09 = reqs["case_09"]
        ident_09 = self.id_mgr.resolve(req_09["email"], req_09["audit_at"])
        res_09 = self.engine.evaluate_case(req_09, ident_09, self.index)
        cited_evidence = [s.evidence_id for s in res_09.steps if s.evidence_id]
        self.assertNotIn("evidence_06", cited_evidence, "case_09 must not cite evidence_06 captured after audit_at")

    def test_02_eligible_file_future_relevant_event_rejected(self):
        """
        2. Eligible file + future relevant event rejected:
        A file captured before audit_at, but whose embedded observation/event occurs after audit_at, is rejected.
        """
        obs_future_event = ResourceObservation(
            file_id="evidence_early",
            captured_at="2026-09-10T12:00:00Z",  # Eligible file
            system_id="account_service",
            resource_id="account_test",
            identifier_matched="user_test",
            state_signal=StateSignal.PRESENT,
            raw_excerpt="test",
            line_ref="test.log:1",
            observed_timestamp="2026-09-20T12:00:00Z"  # Future event
        )
        audit_at = "2026-09-15T12:00:00Z"
        best = self.engine.select_best_observation([obs_future_event], audit_at)
        self.assertIsNone(best, "Future event must be rejected even if file was captured earlier")

    def test_03_both_eligible_accepted(self):
        """
        3. Both eligible accepted:
        Positive control: file captured <= audit_at AND embedded event <= audit_at is accepted.
        """
        obs_valid = ResourceObservation(
            file_id="evidence_valid",
            captured_at="2026-09-10T12:00:00Z",
            system_id="account_service",
            resource_id="account_test",
            identifier_matched="user_test",
            state_signal=StateSignal.PRESENT,
            raw_excerpt="test",
            line_ref="test.log:1",
            observed_timestamp="2026-09-10T12:00:00Z"
        )
        audit_at = "2026-09-15T12:00:00Z"
        best = self.engine.select_best_observation([obs_valid], audit_at)
        self.assertIsNotNone(best, "Observation with eligible file and eligible event must be accepted")
        self.assertEqual(best.resource_id, "account_test")

    def test_04_one_future_only_necessary_trace_source_rejected(self):
        """
        4. One future-only necessary trace source/edge rejected:
        Multi-source traces require every connecting edge to be eligible at audit_at.
        If user link is early but audit link is late, the trace join is rejected.
        """
        trace_assoc = {
            "user_id": "user_trace_test",
            "resource_id": "audit_record_trace_test",
            "file_id": "evidence_trace_a",
            "manifest_captured_at": "2026-09-20T12:00:00Z",  # One edge is future-only
            "captured_at": "2026-09-20T12:00:00Z",
            "embedded_time": "2026-09-01T12:00:00Z",
            "edges": [
                {"role": "user_trace_link", "file_id": "evidence_trace_u", "manifest_captured_at": "2026-09-01T12:00:00Z", "line_ts": "2026-09-01T12:00:00Z"},
                {"role": "audit_record_trace_link", "file_id": "evidence_trace_a", "manifest_captured_at": "2026-09-20T12:00:00Z", "line_ts": "2026-09-20T12:00:00Z"}
            ],
            "locator": "trace:tr-test",
            "retention_until": "2030-01-01T00:00:00Z"
        }
        audit_at = "2026-09-15T12:00:00Z"
        
        # Verify via association eligibility check in evaluate_case
        req = {
            "case_id": "case_trace_test",
            "email": "trace_user@test.com",
            "audit_at": audit_at,
            "requested_at": "2026-08-01T00:00:00Z",
            "request_text": "Please delete all my personal data immediately."
        }
        ident = make_test_ident(user_id="user_trace_test", email="trace_user@test.com", name="Trace User")
        
        # Inject temporarily into audit_records_associations
        self.engine.audit_records_associations.append(trace_assoc)
        try:
            res = self.engine.evaluate_case(req, ident, self.index)
            cited = [s.resource_id for s in res.steps]
            self.assertNotIn("audit_record_trace_test", cited, "Trace with future edge must be rejected")
        finally:
            self.engine.audit_records_associations.remove(trace_assoc)

    def test_05_nested_snapshot_updated_at_cannot_erase_manifest_capture_time(self):
        """
        5. Nested snapshot/updated_at cannot erase manifest capture time:
        A late file cannot be admitted solely because an internal snapshot or updated_at is older.
        Specifically verifies evidence_02 (captured 2026-09-17) is rejected for case_24 (audit_at 2026-09-15).
        """
        with open(os.path.join(DATASET_DIR, "sample_deletion_requests.csv"), "r", encoding="utf-8") as f:
            reqs = {r["case_id"]: r for r in csv.DictReader(f)}
        req_24 = reqs["case_24"]
        ident_24 = self.id_mgr.resolve(req_24["email"], req_24["audit_at"])
        res_24 = self.engine.evaluate_case(req_24, ident_24, self.index)
        cited_evidence = [s.evidence_id for s in res_24.steps if s.evidence_id]
        self.assertNotIn("evidence_02", cited_evidence, "case_24 must not cite evidence_02 captured after audit_at")

    def test_06_later_generated_sidecar_can_represent_eligible_original_source(self):
        """
        6. Later-generated sidecar can represent an eligible original source:
        Sidecar extraction_timestamp (October 2026) is preprocessing metadata.
        Original source capture time (captured_at: 2026-03-10) governs eligibility.
        """
        sidecar_path = os.path.join(REPO_ROOT, "data", "visual_sidecars", "evidence_42.json")
        self.assertTrue(os.path.exists(sidecar_path))
        with open(sidecar_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["captured_at"], "2026-03-10T06:00:00Z")
        self.assertTrue(data["extraction_timestamp"] > "2026-10-01")  # Preprocessing time is later
        
        # Verify parser uses captured_at <= audit_at, admitting the observation
        ident = make_test_ident(user_id="user_17", email="user17@test.com", name="User 17")
        obs = parse_visual_evidence(
            file_path=os.path.join(DATASET_DIR, "evidence", "images", "deleted_account_reference_20260310.png"),
            file_id="evidence_42",
            captured_at="2026-03-10T06:00:00Z",
            identity=ident,
            audit_at="2026-09-15T12:00:00Z"
        )
        self.assertTrue(len(obs) > 0, "Eligible original source via sidecar must be admitted")
        self.assertEqual(obs[0].resource_id, "tombstone_17")

    def test_07_supplied_retention_policy_facts_work_without_particular_field(self):
        """
        7. Supplied retention policy facts work without a particular field:
        When an audit record observation in a snapshot bundle lacks a per-record retention_until,
        the retention period is resolved via the supplied retention register (e.g. from service export / SQL).
        """
        # audit_record_3737 retention fact is supplied via retention_register from service_resource_export
        self.assertIn("audit_record_3737", self.engine.retention_register)
        ret_until, fcap = self.engine.retention_register["audit_record_3737"]
        self.assertEqual(ret_until, "2034-09-30T23:59:59Z")
        self.assertTrue("2026-09-15T12:00:00Z" <= ret_until)

    def test_08_genuinely_unknown_relevant_retention_remains_unresolved(self):
        """
        8. Genuinely unknown relevant retention remains unresolved:
        If a relevant security audit record has no retention period supplied by any record or register,
        the state engine must NOT default to RETAIN or DELETE, but produce BLOCKED_UNKNOWN_POLICY_CONDITION.
        """
        unknown_assoc = {
            "user_id": "user_unknown_ret",
            "resource_id": "audit_record_mystery_9999",
            "file_id": "evidence_test_mystery",
            "manifest_captured_at": "2026-09-01T12:00:00Z",
            "captured_at": "2026-09-01T12:00:00Z",
            "embedded_time": "2026-09-01T12:00:00Z",
            "locator": "test",
            "retention_until": None  # No retention period supplied anywhere
        }
        req = {
            "case_id": "case_unknown_ret",
            "email": "unknown_ret@test.com",
            "audit_at": "2026-09-15T12:00:00Z",
            "requested_at": "2026-08-01T00:00:00Z",
            "request_text": "Please erase all my personal data."
        }
        ident = make_test_ident(user_id="user_unknown_ret", email="unknown_ret@test.com", name="Mystery User")
        
        self.engine.audit_records_associations.append(unknown_assoc)
        try:
            res = self.engine.evaluate_case(req, ident, self.index)
            self.assertEqual(res.verdict_certainty, VerdictCertainty.BLOCKED_UNKNOWN_POLICY_CONDITION)
            self.assertIsNone(res.status, "Case with unknown policy condition must be blocked, not given a status")
        finally:
            self.engine.audit_records_associations.remove(unknown_assoc)

    def test_09_attributable_pre_request_tombstone_not_discarded_solely_for_age(self):
        """
        9. Attributable pre-request tombstone is not discarded solely for age:
        Tombstone tombstone_17 in evidence_42 (captured 2026-03-10) is present at audit_at (2026-09-15)
        for case_17 (requested_at: 2026-08-19). It must remain relevant and be verified as REDACTED.
        """
        with open(os.path.join(DATASET_DIR, "sample_deletion_requests.csv"), "r", encoding="utf-8") as f:
            reqs = {r["case_id"]: r for r in csv.DictReader(f)}
        req_17 = reqs["case_17"]
        ident_17 = self.id_mgr.resolve(req_17["email"], req_17["audit_at"])
        res_17 = self.engine.evaluate_case(req_17, ident_17, self.index)
        
        tombstone_steps = [s for s in res_17.steps if s.resource_id == "tombstone_17"]
        self.assertTrue(len(tombstone_steps) > 0, "Attributable pre-request tombstone must not be discarded")
        self.assertEqual(tombstone_steps[0].operation, "VERIFY_RECORD_REDACTED")
        self.assertEqual(tombstone_steps[0].state, "REDACTED")

    def test_10_relevant_blockers_prevent_publication_and_preserve_existing_output(self):
        """
        10. Relevant blockers prevent publication and preserve existing output:
        When a case has unresolved blockers, process_requests refuses publication
        and preserves the existing target file on disk.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = os.path.join(tmpdir, "candidate_output.csv")
            diag_file = os.path.join(tmpdir, "diagnostics.json")
            with open(out_file, "w", encoding="utf-8") as f:
                f.write("initial_unmodified_content\n")
            
            # Create a request with an unresolvable identity
            reqs_csv = os.path.join(tmpdir, "requests.csv")
            with open(reqs_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["case_id", "email", "requested_at", "reported_status", "reported_at", "audit_at", "request_text"])
                writer.writeheader()
                writer.writerow({
                    "case_id": "case_block_01",
                    "email": "completely_unresolvable_user@test.com",
                    "requested_at": "2026-08-01T00:00:00Z",
                    "reported_status": "COMPLETE",
                    "reported_at": "2026-08-05T00:00:00Z",
                    "audit_at": "2026-09-01T00:00:00Z",
                    "request_text": "I request complete deletion of my account and all personal data."
                })
            
            exit_code = process_requests(
                dataset_dir=DATASET_DIR,
                requests_csv=reqs_csv,
                output_csv=out_file,
                diagnostics_json=diag_file,
                diagnostic_mode=False
            )
            
            self.assertEqual(exit_code, 1, "Expected exit code 1 for publication refusal")
            with open(out_file, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertEqual(content, "initial_unmodified_content\n", "Output file must be preserved unmodified")


if __name__ == "__main__":
    unittest.main()
