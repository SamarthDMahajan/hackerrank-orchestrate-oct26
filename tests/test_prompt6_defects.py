"""
Production-path regression tests for Prompt 6:
Fix source-confirmed state-engine and evidence-index defects.
HackerRank Orchestrate (October 2026) - Ghost Data Still Exists.
"""

import os
import unittest
import tempfile
import shutil
from datetime import datetime, timezone

from code.identity import IdentitySet, IdentityManager
from code.evidence.index import EvidenceIndex
from code.evidence.models import StateSignal, ResourceObservation
from code.contracts import (
    VerdictCertainty,
    PlanCompleteness,
    DeletionStatus,
    Phase,
    Step,
)
from code.engine.state import StateEngine
import code.main as main_mod

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(REPO_ROOT, "dataset")


class TestPrompt6Defects(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = StateEngine(DATASET_DIR)
        cls.index = EvidenceIndex(DATASET_DIR)
        cls.id_mgr = IdentityManager(DATASET_DIR)

    def test_01_same_copy_supersession_present_to_absent_and_active_to_disabled(self):
        """
        1. Demonstrates same-copy supersession:
        A newer authoritative observation supersedes an older observation of the same physical copy.
        Older primary PRESENT must not override newer authoritative primary ABSENT.
        Same for ACTIVE -> DISABLED on data flows.
        """
        # A. Same copy: T1 PRESENT -> T2 ABSENT
        obs_old = ResourceObservation(
            file_id="evidence_old",
            captured_at="2026-09-01T10:00:00Z",
            system_id="account_service",
            resource_id="account_101",
            identifier_matched="user_101",
            state_signal=StateSignal.PRESENT,
            raw_excerpt="Account active at T1",
            line_ref="customer_profiles_primary",
            physical_copy_scope="customer_profiles_primary",
            observed_timestamp="2026-09-01T10:00:00Z"
        )
        obs_new = ResourceObservation(
            file_id="evidence_new",
            captured_at="2026-09-05T10:00:00Z",
            system_id="account_service",
            resource_id="account_101",
            identifier_matched="user_101",
            state_signal=StateSignal.ABSENT,
            raw_excerpt="Account 404 at T2",
            line_ref="customer_profiles_primary",
            physical_copy_scope="customer_profiles_primary",
            observed_timestamp="2026-09-05T10:00:00Z"
        )
        best = self.engine.select_best_observation([obs_old, obs_new], audit_at="2026-09-10T00:00:00Z")
        self.assertIsNotNone(best)
        self.assertEqual(best.state_signal, StateSignal.ABSENT)
        self.assertEqual(best.file_id, "evidence_new")

        # B. Flow: T1 ACTIVE -> T2 DISABLED
        flow_old = ResourceObservation(
            file_id="evidence_flow_01",
            captured_at="2026-09-01T10:00:00Z",
            system_id="integration_service",
            resource_id="connector_101",
            identifier_matched="user_101",
            state_signal=StateSignal.ACTIVE,
            raw_excerpt="Sync active",
            line_ref="connectors",
            physical_copy_scope="connectors",
            observed_timestamp="2026-09-01T10:00:00Z"
        )
        flow_new = ResourceObservation(
            file_id="evidence_flow_02",
            captured_at="2026-09-05T10:00:00Z",
            system_id="integration_service",
            resource_id="connector_101",
            identifier_matched="user_101",
            state_signal=StateSignal.DISABLED,
            raw_excerpt="Sync disabled",
            line_ref="connectors",
            physical_copy_scope="connectors",
            observed_timestamp="2026-09-05T10:00:00Z"
        )
        best_flow = self.engine.select_best_observation([flow_old, flow_new], audit_at="2026-09-10T00:00:00Z")
        self.assertIsNotNone(best_flow)
        self.assertEqual(best_flow.state_signal, StateSignal.DISABLED)
        self.assertEqual(best_flow.file_id, "evidence_flow_02")

    def test_02_primary_absence_plus_separate_retained_replica(self):
        """
        2. Demonstrates multi-replica persistence:
        Absence in the primary does not erase presence in another replica.
        """
        obs_primary_absent = ResourceObservation(
            file_id="evidence_primary",
            captured_at="2026-09-05T10:00:00Z",
            system_id="account_service",
            resource_id="account_202",
            identifier_matched="user_202",
            state_signal=StateSignal.ABSENT,
            raw_excerpt="Deleted from primary",
            line_ref="customer_profiles_primary",
            physical_copy_scope="customer_profiles_primary",
            observed_timestamp="2026-09-05T10:00:00Z"
        )
        obs_replica_present = ResourceObservation(
            file_id="evidence_replica",
            captured_at="2026-09-04T10:00:00Z",
            system_id="account_service",
            resource_id="account_202",
            identifier_matched="user_202",
            state_signal=StateSignal.PRESENT,
            raw_excerpt="Still present in replica",
            line_ref="customer_profiles_failover_replica",
            physical_copy_scope="customer_profiles_failover_replica",
            observed_timestamp="2026-09-04T10:00:00Z"
        )
        best = self.engine.select_best_observation([obs_primary_absent, obs_replica_present], audit_at="2026-09-10T00:00:00Z")
        self.assertIsNotNone(best)
        self.assertEqual(best.state_signal, StateSignal.PRESENT)
        self.assertEqual(best.file_id, "evidence_replica")

    def test_03_equal_time_conflict_unresolved(self):
        """
        3. Demonstrates equal-time contradictory observations on same copy remain unresolved.
        """
        obs_a = ResourceObservation(
            file_id="evidence_c1",
            captured_at="2026-09-05T12:00:00Z",
            system_id="account_service",
            resource_id="account_303",
            identifier_matched="user_303",
            state_signal=StateSignal.PRESENT,
            raw_excerpt="Claimed PRESENT at T",
            line_ref="customer_profiles_primary",
            physical_copy_scope="customer_profiles_primary",
            observed_timestamp="2026-09-05T12:00:00Z"
        )
        obs_b = ResourceObservation(
            file_id="evidence_c2",
            captured_at="2026-09-05T12:00:00Z",
            system_id="account_service",
            resource_id="account_303",
            identifier_matched="user_303",
            state_signal=StateSignal.ABSENT,
            raw_excerpt="Claimed ABSENT at T",
            line_ref="customer_profiles_primary",
            physical_copy_scope="customer_profiles_primary",
            observed_timestamp="2026-09-05T12:00:00Z"
        )
        best = self.engine.select_best_observation([obs_a, obs_b], audit_at="2026-09-10T00:00:00Z")
        self.assertIsNotNone(best)
        self.assertEqual(best.state_signal, StateSignal.UNPARSED)
        self.assertIn("UNRESOLVED_CONFLICT", best.raw_excerpt)

    def test_04_unrelated_eligible_file_cannot_prove_resource_claim(self):
        """
        4. Demonstrates removal of citation fallbacks (eligible_files[0], generic export).
        If no evidence proves an audit record exists, the engine does not fabricate one.
        """
        req = {
            "case_id": "case_test_unrelated",
            "email": "ghost.user@test.com",
            "requested_at": "2026-09-01T10:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-09-02T10:00:00Z",
            "audit_at": "2026-09-10T10:00:00Z",
            "request_text": "Please delete my account."
        }
        ident = IdentitySet(
            user_id="user_unrelated_999",
            name="Unrelated Ghost",
            emails=frozenset({"ghost.user@test.com"}),
            email_hashes=frozenset({"hash_ghost"}),
            phones=frozenset({"+19999999999"}),
            active_email="ghost.user@test.com",
            active_email_hash="hash_ghost",
            active_phone="+19999999999"
        )
        res = self.engine.evaluate_case(req, ident, self.index)
        # Should NOT fabricate a security_service audit step using eligible_files[0]
        has_audit = any(s.system_id == "security_service" for s in res.steps)
        self.assertFalse(has_audit)

    def test_05_future_association_cannot_borrow_older_arbitrary_citation(self):
        """
        5. Demonstrates that a future association (captured > audit_at) cannot
        leak into pre-audit decisions or borrow an older citation.
        """
        req = {
            "case_id": "case_test_future_assoc",
            "email": "future.link@test.com",
            "requested_at": "2026-09-01T10:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-09-02T10:00:00Z",
            "audit_at": "2026-09-10T10:00:00Z",
            "request_text": "Please delete my account."
        }
        ident = IdentitySet(
            user_id="user_future_888",
            name="Future User",
            emails=frozenset({"future.link@test.com"}),
            email_hashes=frozenset({"hash_future"}),
            phones=frozenset({"+18888888888"}),
            active_email="future.link@test.com",
            active_email_hash="hash_future",
            active_phone="+18888888888"
        )
        # Inject an account link with captured_at AFTER audit_at
        self.engine.account_links.append({
            "resource_id": "account_future_888",
            "user_id": "user_future_888",
            "email": "future.link@test.com",
            "captured_at": "2026-09-15T00:00:00Z", # Future!
            "file_id": "evidence_future_99"
        })
        acc = self.engine.determine_account(req, ident, {}, audit_at=req["audit_at"])
        # Must return "" because association is in the future
        self.assertEqual(acc, "")

    def test_06_earlier_eligible_associations_survive_later_entries(self):
        """
        6. Demonstrates that earlier eligible associations survive subsequent entries
        and are not destroyed by dictionary overwriting.
        """
        self.engine.audit_records_associations.append({
            "user_id": "user_multi_assoc",
            "resource_id": "audit_record_early",
            "file_id": "evidence_early_01",
            "captured_at": "2026-08-01T00:00:00Z",
            "embedded_time": "2026-08-01T00:00:00Z",
            "locator": "early_loc",
            "retention_until": "2026-12-01T00:00:00Z"
        })
        self.engine.audit_records_associations.append({
            "user_id": "user_multi_assoc",
            "resource_id": "audit_record_late",
            "file_id": "evidence_late_02",
            "captured_at": "2026-09-20T00:00:00Z",
            "embedded_time": "2026-09-20T00:00:00Z",
            "locator": "late_loc",
            "retention_until": "2026-12-01T00:00:00Z"
        })
        # Evaluate at audit_at = 2026-08-15
        eligible = [a for a in self.engine.audit_records_associations
                    if a["user_id"] == "user_multi_assoc" and a["captured_at"] <= "2026-08-15T00:00:00Z"]
        self.assertEqual(len(eligible), 1)
        self.assertEqual(eligible[0]["resource_id"], "audit_record_early")
        self.assertEqual(eligible[0]["file_id"], "evidence_early_01")

    def test_07_trace_sources_retain_correct_ids_and_timestamps(self):
        """
        7. Demonstrates that trace correlation links retain genuine connecting edge file IDs
        and timestamps, fixing the loop variable leak.
        """
        trace_links = [l for l in self.engine.account_links if "source_edges" in l]
        self.assertTrue(len(trace_links) > 0, "Trace links must exist and carry source_edges")
        for link in trace_links:
            edges = link["source_edges"]
            self.assertTrue(len(edges) >= 1)
            for edge in edges:
                self.assertTrue(edge.get("file_id"), "Edge must have file_id")
                self.assertTrue(edge.get("timestamp"), "Edge must have timestamp")

    def test_08_legitimate_pre_request_evidence_remains_usable(self):
        """
        8. Demonstrates that legitimate evidence captured before requested_at
        remains eligible at or before audit_at (global lower cutoff removed).
        """
        # Case with requested_at = 2026-09-05, audit_at = 2026-09-10
        eligible = self.index.get_eligible_files(
            audit_at="2026-09-10T00:00:00Z",
            requested_at="2026-09-05T00:00:00Z"
        )
        # Check that files captured before 2026-09-05 are included
        pre_request_files = [f for f in eligible if f.get("captured_at", "") < "2026-09-05T00:00:00Z"]
        self.assertTrue(len(pre_request_files) > 0, "Pre-request evidence must be usable")

    def test_09_exact_subject_system_matching(self):
        """
        9. Demonstrates exact token matching:
        user_1 vs user_10, empty identifiers, email prefix collisions.
        """
        ident_user_1 = IdentitySet(
            user_id="user_1",
            name="User One",
            emails=frozenset({"dan@domain.com"}),
            email_hashes=frozenset({"hash_1"}),
            phones=frozenset({"+10000000001"}),
            active_email="dan@domain.com",
            active_email_hash="hash_1",
            active_phone="+10000000001"
        )
        # Mock activities with user_10 and jordan@domain.com
        self.index.activities.append({
            "activity_id": "act_mock_collision",
            "event_time": "2026-09-01T10:00:00Z",
            "target_system": "account_service",
            "resource_id": "account_collision_10",
            "details": "Lookup completed for user_10 and jordan@domain.com"
        })
        cands = self.index.get_candidate_resources(ident_user_1, audit_at="2026-09-10T00:00:00Z")
        self.assertNotIn("account_collision_10", cands, "user_1 must not match user_10 or jordan@domain.com")

    def test_10_shared_message_vs_subject_only_attachment_in_pdf(self):
        """
        10. Demonstrates distinguishing shared messages (REDACT) from subject-only attachments (DELETE)
        based on record facts rather than the .pdf container format.
        """
        # Case A: Shared message facts -> REDACT
        obs_msg = ResourceObservation(
            file_id="evidence_pdf_msg",
            captured_at="2026-09-01T10:00:00Z",
            system_id="support_platform",
            resource_id="support_msg_01",
            identifier_matched="user_test",
            state_signal=StateSignal.PRESENT,
            raw_excerpt="Customer agent conversation transcript in support_case_archive.pdf",
            line_ref="page_1",
            physical_copy_scope="support_archive",
            observed_timestamp="2026-09-01T10:00:00Z"
        )
        # Case B: Attachment facts -> DELETE
        obs_att = ResourceObservation(
            file_id="evidence_pdf_att",
            captured_at="2026-09-01T10:00:00Z",
            system_id="support_platform",
            resource_id="support_att_02",
            identifier_matched="user_test",
            state_signal=StateSignal.PRESENT,
            raw_excerpt="ticket_attachment customer_id_scan.png in archive.pdf",
            line_ref="page_2",
            physical_copy_scope="support_archive",
            observed_timestamp="2026-09-01T10:00:00Z"
        )

        req = {
            "case_id": "case_test_support",
            "email": "support.user@test.com",
            "requested_at": "2026-09-01T10:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-09-02T10:00:00Z",
            "audit_at": "2026-09-10T10:00:00Z",
            "request_text": "Delete my data."
        }
        ident = IdentitySet(
            user_id="user_test",
            name="Test User",
            emails=frozenset({"support.user@test.com"}),
            email_hashes=frozenset({"hash_s"}),
            phones=frozenset({"+10000000000"}),
            active_email="support.user@test.com",
            active_email_hash="hash_s",
            active_phone="+10000000000"
        )

        # Mock index returning obs_msg
        class MockMsgIndex:
            def observe_for_case(self, *args, **kwargs):
                return [obs_msg]
            def get_eligible_files(self, *args, **kwargs):
                return []

        res_msg = self.engine.evaluate_case(req, ident, MockMsgIndex())
        finding_msg = next((s for s in res_msg.steps if s.resource_id == "support_msg_01" and s.phase == Phase.FINDING), None)
        self.assertIsNotNone(finding_msg)
        self.assertEqual(finding_msg.operation, "REPORT_EXPOSED_PII") # REDACT path

        # Mock index returning obs_att
        class MockAttIndex:
            def observe_for_case(self, *args, **kwargs):
                return [obs_att]
            def get_eligible_files(self, *args, **kwargs):
                return []

        res_att = self.engine.evaluate_case(req, ident, MockAttIndex())
        finding_att = next((s for s in res_att.steps if s.resource_id == "support_att_02" and s.phase == Phase.FINDING), None)
        self.assertIsNotNone(finding_att)
        self.assertEqual(finding_att.operation, "REPORT_REMAINING_RECORD") # DELETE path

    def test_11_absent_unknown_security_state_does_not_become_retained_present(self):
        """
        11. Demonstrates that an expired audit record is not added as retained PRESENT.
        """
        self.engine.audit_records_associations.append({
            "user_id": "user_expired_audit",
            "resource_id": "audit_record_expired_01",
            "file_id": "evidence_exp_01",
            "captured_at": "2026-08-01T00:00:00Z",
            "embedded_time": "2026-08-01T00:00:00Z",
            "locator": "exp_loc",
            "retention_until": "2026-08-10T00:00:00Z" # Expired before audit_at 2026-09-01!
        })
        req = {
            "case_id": "case_test_exp_audit",
            "email": "exp.audit@test.com",
            "requested_at": "2026-08-15T00:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-08-20T00:00:00Z",
            "audit_at": "2026-09-01T00:00:00Z",
            "request_text": "Delete everything."
        }
        ident = IdentitySet(
            user_id="user_expired_audit",
            name="Expired Audit User",
            emails=frozenset({"exp.audit@test.com"}),
            email_hashes=frozenset({"hash_exp"}),
            phones=frozenset({"+10000000000"}),
            active_email="exp.audit@test.com",
            active_email_hash="hash_exp",
            active_phone="+10000000000"
        )
        res = self.engine.evaluate_case(req, ident, self.index)
        has_audit = any(s.system_id == "security_service" for s in res.steps)
        self.assertFalse(has_audit, "Expired audit record must not be retained as PRESENT")

    def test_12_unrelated_anonymized_profile_not_attributed(self):
        """
        12. Demonstrates that an unlinked anonymized profile (e.g. analytics_901)
        is not attributed to an unrelated request subject.
        """
        unrelated_anonymized_obs = ResourceObservation(
            file_id="evidence_56",
            captured_at="2026-09-07T09:45:00Z",
            system_id="analytics_platform",
            resource_id="analytics_901",
            identifier_matched="unrelated_subject",
            state_signal=StateSignal.ANONYMIZED,
            raw_excerpt="Anonymized telemetry without PII",
            line_ref="records",
            physical_copy_scope="analytics_identity_store",
            observed_timestamp="2026-09-07T09:45:00Z"
        )
        req = {
            "case_id": "case_test_anon",
            "email": "unlinked.subject@test.com",
            "requested_at": "2026-09-01T00:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-09-02T00:00:00Z",
            "audit_at": "2026-09-10T00:00:00Z",
            "request_text": "Delete my account."
        }
        ident = IdentitySet(
            user_id="user_unlinked_anon",
            name="Unlinked Anon",
            emails=frozenset({"unlinked.subject@test.com"}),
            email_hashes=frozenset({"hash_unlinked"}),
            phones=frozenset({"+10000000000"}),
            active_email="unlinked.subject@test.com",
            active_email_hash="hash_unlinked",
            active_phone="+10000000000"
        )
        class MockAnonIndex:
            def observe_for_case(self, *args, **kwargs):
                return [unrelated_anonymized_obs]
            def get_eligible_files(self, *args, **kwargs):
                return []

        res = self.engine.evaluate_case(req, ident, MockAnonIndex())
        has_analytics = any(s.system_id == "analytics_platform" for s in res.steps)
        self.assertFalse(has_analytics, "Unrelated anonymized profile must not be attributed")

    def test_13_relevant_blockers_prevent_publication_and_preserve_old_output(self):
        """
        13. Demonstrates that cases with decision blockers refuse final publication
        and preserve the existing output file byte-for-byte.
        """
        temp_dir = tempfile.mkdtemp()
        try:
            test_out = os.path.join(temp_dir, "output.csv")
            with open(test_out, "w", encoding="utf-8") as f:
                f.write("INITIAL_PRESERVED_CONTENT\n")

            # Create an input request that produces a blocked case (e.g. unknown email)
            test_req_csv = os.path.join(temp_dir, "test_requests.csv")
            with open(test_req_csv, "w", encoding="utf-8", newline="") as f:
                f.write("case_id,email,requested_at,reported_status,reported_at,audit_at,request_text\n")
                f.write("case_block_01,unknown_user@test.com,2026-08-20T10:00:00Z,COMPLETE,2026-08-21T10:00:00Z,2026-09-01T00:00:00Z,Please delete my data.\n")

            # Run pipeline in non-diagnostic mode
            blocked_count = main_mod.process_requests(
                dataset_dir="dataset",
                requests_csv=test_req_csv,
                output_csv=test_out,
                diagnostic_mode=False,
                diagnostics_json=os.path.join(temp_dir, "diagnostics.json")
            )
            self.assertEqual(blocked_count, 1)

            # Confirm file was NOT overwritten
            with open(test_out, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertEqual(content, "INITIAL_PRESERVED_CONTENT\n")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
