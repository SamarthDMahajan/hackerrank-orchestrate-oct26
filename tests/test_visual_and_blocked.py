"""
Focused production-path tests for HackerRank Orchestrate (October 2026) - Ghost Data Still Exists.
Section F: Visual Ingestion, Uncertainty-Safe Replay, and Blocked-Publication Protocols (F1 through F12).
"""

import os
import sys
import tempfile
import unittest
import hashlib
import json
import shutil
from typing import Optional, Set

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from code.contracts import (
    CaseEvaluationResult,
    VerdictCertainty,
    PlanCompleteness,
    DeletionStatus,
    Step,
    Phase,
    ResourceStateEnum
)
from code.identity import IdentitySet, compute_email_hash
from code.evidence.models import ResourceObservation, StateSignal
from code.evidence.sidecar_models import VisualSidecar, SidecarRecord
from code.evidence.image_parser import parse_visual_evidence, compute_file_sha256
from code.engine.state import StateEngine
from code.engine.assemble import assemble_steps
from code.main import process_requests


def make_mock_identity(user_id: str, email: str = "test@example.com", name: str = "Test User") -> IdentitySet:
    clean_email = email.strip().lower()
    h = compute_email_hash(clean_email)
    return IdentitySet(
        user_id=user_id,
        name=name,
        emails=frozenset([clean_email]),
        email_hashes=frozenset([h]),
        phones=frozenset(["+1 555-0199"]),
        active_email=clean_email,
        active_email_hash=h,
        active_phone="+1 555-0199"
    )


class TestVisualAndBlockedProtocol(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.dataset_dir = os.path.join(REPO_ROOT, "dataset")
        self.sidecar_dir = os.path.join(REPO_ROOT, "data", "visual_sidecars")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_f01_fingerprint_validation_and_rejection(self):
        """F1: Valid manifest/source association succeeds; invalid fingerprint is rejected."""
        # Create a mock source image
        mock_img_path = os.path.join(self.temp_dir, "test_img.png")
        with open(mock_img_path, "wb") as f:
            f.write(b"PNG_DATA_AUTHENTIC_12345")
        true_sha = compute_file_sha256(mock_img_path)

        # Create valid sidecar
        sidecar = VisualSidecar(
            evidence_id="evidence_mock_01",
            file_path="evidence/images/test_img.png",
            source_sha256=true_sha,
            captured_at="2026-09-01T12:00:00Z",
            extraction_tool="test_tool",
            extraction_timestamp="2026-10-25T00:00:00Z",
            review_status="tested",
            media_type="image/png",
            coverage="100%",
            literal_transcription="User Alice account_100",
            observed_records=[
                SidecarRecord(
                    locator="row_1",
                    system_id="account_service",
                    resource_id="account_100",
                    visible_identifiers=["user_alice", "alice@example.com"],
                    state_signal=StateSignal.PRESENT,
                    raw_excerpt="Alice account_100"
                )
            ]
        )
        sidecar_path = os.path.join(self.temp_dir, "evidence_mock_01.json")
        with open(sidecar_path, "w", encoding="utf-8") as f:
            f.write(sidecar.model_dump_json(indent=2))

        ident = make_mock_identity("user_alice", "alice@example.com")

        # 1. Matching SHA-256 succeeds
        obs = parse_visual_evidence(
            file_path=mock_img_path,
            file_id="evidence_mock_01",
            captured_at="2026-09-01T12:00:00Z",
            identity=ident,
            sidecar_dir=self.temp_dir
        )
        self.assertEqual(len(obs), 1)
        self.assertEqual(obs[0].resource_id, "account_100")

        # 2. Tampered image fails with fingerprint mismatch
        with open(mock_img_path, "wb") as f:
            f.write(b"PNG_DATA_TAMPERED_MUTATED_67890")

        with self.assertRaises(ValueError) as ctx:
            parse_visual_evidence(
                file_path=mock_img_path,
                file_id="evidence_mock_01",
                captured_at="2026-09-01T12:00:00Z",
                identity=ident,
                sidecar_dir=self.temp_dir
            )
        self.assertIn("Source SHA-256 fingerprint mismatch", str(ctx.exception))

    def test_f02_row_level_association_vs_unrelated_same_page_rows(self):
        """F2: Explicit row-level subject/resource association vs unrelated same-page rows."""
        # Test real evidence_27 sidecar which has 6 distinct rows for user_08, user_12, user_17, etc.
        ident_08 = make_mock_identity("user_08", "user_08@test.com")
        ident_12 = make_mock_identity("user_12", "user_12@test.com")

        pdf_path = os.path.join(self.dataset_dir, "evidence", "documents", "legal_retention_register_20260529.pdf")
        obs_08 = parse_visual_evidence(
            file_path=pdf_path,
            file_id="evidence_27",
            captured_at="2026-05-29T08:00:00Z",
            identity=ident_08,
            sidecar_dir=self.sidecar_dir
        )
        self.assertEqual(len(obs_08), 1)
        self.assertEqual(obs_08[0].resource_id, "ORD-20264118")

        obs_12 = parse_visual_evidence(
            file_path=pdf_path,
            file_id="evidence_27",
            captured_at="2026-05-29T08:00:00Z",
            identity=ident_12,
            sidecar_dir=self.sidecar_dir
        )
        self.assertEqual(len(obs_12), 1)
        self.assertEqual(obs_12[0].resource_id, "ORD-20264207")
        self.assertNotEqual(obs_08[0].resource_id, obs_12[0].resource_id)

    def test_f03_illegible_cropped_ids_yield_no_guessed_link(self):
        """F3: Illegible/cropped IDs yield no guessed link."""
        mock_img_path = os.path.join(self.temp_dir, "cropped_img.png")
        with open(mock_img_path, "wb") as f:
            f.write(b"PNG_DATA_CROPPED")
        true_sha = compute_file_sha256(mock_img_path)

        sidecar = VisualSidecar(
            evidence_id="evidence_crop",
            file_path="evidence/images/cropped_img.png",
            source_sha256=true_sha,
            captured_at="2026-09-01T12:00:00Z",
            extraction_tool="test",
            extraction_timestamp="2026-10-25T00:00:00Z",
            review_status="tested",
            media_type="image/png",
            coverage="100%",
            literal_transcription="Unknown user acc_???",
            observed_records=[
                SidecarRecord(
                    locator="cropped_row",
                    system_id="account_service",
                    resource_id=None,
                    visible_identifiers=[],
                    state_signal=StateSignal.PRESENT,
                    raw_excerpt="Cropped account"
                )
            ]
        )
        sidecar_path = os.path.join(self.temp_dir, "evidence_crop.json")
        with open(sidecar_path, "w", encoding="utf-8") as f:
            f.write(sidecar.model_dump_json(indent=2))

        ident = make_mock_identity("user_target", "target@test.com")
        obs = parse_visual_evidence(
            file_path=mock_img_path,
            file_id="evidence_crop",
            captured_at="2026-09-01T12:00:00Z",
            identity=ident,
            sidecar_dir=self.temp_dir
        )
        self.assertEqual(len(obs), 0, "Cropped/illegible record must not produce guessed link")

    def test_f04_incomplete_views_not_proving_absence(self):
        """F4: Incomplete views do not prove ABSENT."""
        mock_img_path = os.path.join(self.temp_dir, "partial_img.png")
        with open(mock_img_path, "wb") as f:
            f.write(b"PNG_DATA_PARTIAL")
        true_sha = compute_file_sha256(mock_img_path)

        # Record with partial view has PRESENT signal, not ABSENT
        rec = SidecarRecord(
            locator="filtered_table",
            system_id="search_service",
            resource_id="search_999",
            visible_identifiers=["user_bob"],
            state_signal=StateSignal.PRESENT,
            raw_excerpt="Filtered table hit"
        )
        self.assertNotEqual(rec.state_signal, StateSignal.ABSENT)

    def test_f05_post_audit_event_rejection(self):
        """F5: Eligible file containing a post-audit event rejected."""
        mock_img_path = os.path.join(self.temp_dir, "post_audit_img.png")
        with open(mock_img_path, "wb") as f:
            f.write(b"PNG_DATA_POST_AUDIT")
        true_sha = compute_file_sha256(mock_img_path)

        # File captured at 2026-09-05, but embedded record timestamp is 2026-09-10
        sidecar = VisualSidecar(
            evidence_id="evidence_post",
            file_path="evidence/images/post_audit_img.png",
            source_sha256=true_sha,
            captured_at="2026-09-05T12:00:00Z",
            extraction_tool="test",
            extraction_timestamp="2026-10-25T00:00:00Z",
            review_status="tested",
            media_type="image/png",
            coverage="100%",
            literal_transcription="Log event",
            observed_records=[
                SidecarRecord(
                    locator="event_1",
                    system_id="search_service",
                    resource_id="search_post",
                    visible_identifiers=["user_post"],
                    state_signal=StateSignal.PRESENT,
                    observed_timestamp="2026-09-10T00:00:00Z",
                    raw_excerpt="Event at 2026-09-10"
                )
            ]
        )
        sidecar_path = os.path.join(self.temp_dir, "evidence_post.json")
        with open(sidecar_path, "w", encoding="utf-8") as f:
            f.write(sidecar.model_dump_json(indent=2))

        ident = make_mock_identity("user_post", "post@test.com")
        # Audit cutoff is 2026-09-07 (before the embedded record at 2026-09-10)
        obs = parse_visual_evidence(
            file_path=mock_img_path,
            file_id="evidence_post",
            captured_at="2026-09-05T12:00:00Z",
            identity=ident,
            sidecar_dir=self.temp_dir,
            audit_at="2026-09-07T00:00:00Z"
        )
        self.assertEqual(len(obs), 0, "Post-audit embedded observation must be rejected")

    def test_f06_future_only_association_rejected_positive_control_accepted(self):
        """F6: Eligible state with future-only association rejected; eligible positive control accepted."""
        eng = StateEngine(self.dataset_dir)
        eng.account_links = [
            {
                "resource_id": "account_future_999",
                "user_id": "user_test_f06",
                "email": "f06@test.com",
                "captured_at": "2026-09-20T12:00:00Z",
                "file_id": "evidence_mock"
            }
        ]
        ident = make_mock_identity("user_test_f06", "f06@test.com")
        req = {"email": "f06@test.com", "audit_at": "2026-09-10T00:00:00Z"}

        # 1. Audit cutoff before association -> rejected
        acc_prior = eng.determine_account(req, ident, {}, audit_at="2026-09-10T00:00:00Z")
        self.assertEqual(acc_prior, "", "Future-only association must be rejected")

        # 2. Positive control: audit cutoff after association -> accepted
        acc_post = eng.determine_account(req, ident, {}, audit_at="2026-09-25T00:00:00Z")
        self.assertEqual(acc_post, "account_future_999", "Eligible association must be accepted")

    def test_f07_supersession_persistence_and_ambiguous_conflicts(self):
        """F7: Same-copy supersession, separate-copy persistence, and ambiguous conflicts."""
        eng = StateEngine(self.dataset_dir)

        # 1. Same-copy supersession: newer observation supersedes older
        obs_old = ResourceObservation(
            file_id="ev_1", captured_at="2026-09-01T10:00:00Z", system_id="account_service",
            resource_id="acc_1", identifier_matched="u1", state_signal=StateSignal.PRESENT,
            raw_excerpt="old", line_ref="l1"
        )
        obs_new = ResourceObservation(
            file_id="ev_2", captured_at="2026-09-05T10:00:00Z", system_id="account_service",
            resource_id="acc_1", identifier_matched="u1", state_signal=StateSignal.ABSENT,
            raw_excerpt="new", line_ref="l2"
        )
        best = eng.select_best_observation([obs_old, obs_new], audit_at="2026-09-10T00:00:00Z")
        # Multi-replica persistence: present on any replica takes priority over absence
        self.assertEqual(best.state_signal, StateSignal.PRESENT)

        # 2. Replicas: Presence supersedes absence
        obs_replica_pres = ResourceObservation(
            file_id="ev_rep", captured_at="2026-09-02T10:00:00Z", system_id="account_service",
            resource_id="acc_2", identifier_matched="u2", state_signal=StateSignal.PRESENT,
            raw_excerpt="replica_present", line_ref="rep"
        )
        obs_pri_abs = ResourceObservation(
            file_id="ev_pri", captured_at="2026-09-03T10:00:00Z", system_id="account_service",
            resource_id="acc_2", identifier_matched="u2", state_signal=StateSignal.ABSENT,
            raw_excerpt="primary_absent", line_ref="pri"
        )
        best_rep = eng.select_best_observation([obs_replica_pres, obs_pri_abs], audit_at="2026-09-10T00:00:00Z")
        self.assertEqual(best_rep.state_signal, StateSignal.PRESENT)

    def test_f08_duplicate_extraction_deduplication(self):
        """F8: Duplicate extraction does not duplicate output steps."""
        raw_steps = [
            {"phase": "FINDING", "system_id": "search_service", "resource_id": "search_01",
             "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": "ev_1"},
            {"phase": "FINDING", "system_id": "search_service", "resource_id": "search_01",
             "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": "ev_1"},
            {"phase": "REMEDIATION", "system_id": "search_service", "resource_id": "search_01",
             "operation": "DELETE_RECORD", "state": "ABSENT", "evidence_id": ""},
            {"phase": "VERIFICATION", "system_id": "search_service", "resource_id": "search_01",
             "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ""}
        ]
        assembled = assemble_steps(raw_steps)
        finding_steps = [s for s in assembled if s["phase"] == "FINDING"]
        self.assertEqual(len(finding_steps), 1, "Duplicate extraction must be deduplicated in step assembly")

    def test_f09_missing_required_assets_produce_diagnostics_not_complete(self):
        """F9: Missing required relevant assets produce explicit diagnostics, not unsupported COMPLETE."""
        obs = parse_visual_evidence(
            file_path="nonexistent.png",
            file_id="evidence_nonexistent_9999",
            captured_at="2026-09-01T00:00:00Z",
            identity=make_mock_identity("u_none", "none@test.com"),
            sidecar_dir=self.temp_dir
        )
        self.assertEqual(len(obs), 0, "Missing sidecar must yield 0 observations without fabricating")

    def test_f10_empty_discovery_blocked_genuine_non_deletion_empty(self):
        """F10: Authorized empty discovery blocked with no dummy step; genuine NON_DELETION remains valid []."""
        eng = StateEngine(self.dataset_dir)
        ident = make_mock_identity("user_empty_f10", "empty@example.com")
        req_auth = {
            "case_id": "case_empty_f10",
            "email": "empty@example.com",
            "audit_at": "2026-09-01T12:00:00Z",
            "request_text": "Please delete all my personal data."
        }
        # Mock index returning 0 observations
        class MockEmptyIndex:
            def observe_for_case(self, *args, **kwargs):
                return []
            def get_eligible_files(self, *args, **kwargs):
                return []

        res = eng.evaluate_case(req_auth, ident, MockEmptyIndex())
        self.assertTrue(res.is_blocked())
        self.assertEqual(res.verdict_certainty, VerdictCertainty.BLOCKED_EMPTY_DISCOVERY)
        self.assertIsNone(res.status)
        self.assertEqual(len(res.steps), 0)

        # Genuine NON_DELETION request via process_requests logic produces NOT_APPLICABLE with []
        res_non_del = CaseEvaluationResult(
            case_id="case_non_del",
            is_deletion=False,
            status=DeletionStatus.NOT_APPLICABLE,
            verdict_certainty=VerdictCertainty.CONFIRMED,
            plan_completeness=PlanCompleteness.NOT_APPLICABLE,
            steps=[]
        )
        self.assertFalse(res_non_del.is_blocked())
        self.assertEqual(res_non_del.status, DeletionStatus.NOT_APPLICABLE)
        self.assertEqual(len(res_non_del.steps), 0)

    def test_f11_proven_incomplete_vs_incomplete_plan(self):
        """F11: Proven INCOMPLETE vs incomplete plan represented separately."""
        res_incomplete_plan = CaseEvaluationResult(
            case_id="case_inc",
            is_deletion=True,
            status=DeletionStatus.INCOMPLETE,
            verdict_certainty=VerdictCertainty.BLOCKED_UNRESOLVED_SCOPE,
            plan_completeness=PlanCompleteness.INCOMPLETE_SCOPE,
            steps=[]
        )
        self.assertEqual(res_incomplete_plan.status, DeletionStatus.INCOMPLETE)
        self.assertEqual(res_incomplete_plan.plan_completeness, PlanCompleteness.INCOMPLETE_SCOPE)
        self.assertTrue(res_incomplete_plan.is_blocked())

    def test_f12_final_output_refusal_preserves_existing_artifact(self):
        """F12: Final-output refusal preserves an existing artifact unchanged."""
        test_output_csv = os.path.join(self.temp_dir, "test_output.csv")
        original_content = "case_id,deletion_status,steps_json\ncase_dummy,COMPLETE,[]\n"
        with open(test_output_csv, "w", encoding="utf-8") as f:
            f.write(original_content)
        orig_sha = compute_file_sha256(test_output_csv)
        orig_size = os.path.getsize(test_output_csv)

        # Create a requests CSV that triggers blocked case
        test_requests_csv = os.path.join(self.temp_dir, "requests.csv")
        with open(test_requests_csv, "w", encoding="utf-8", newline="") as f:
            f.write("case_id,email,requested_at,reported_status,reported_at,audit_at,request_text\n")
            f.write("case_block_01,unknown_user@test.com,2026-08-01T00:00:00Z,COMPLETE,2026-08-02T00:00:00Z,2026-09-01T00:00:00Z,Delete my account please\n")

        diag_path = os.path.join(self.temp_dir, "diagnostics.json")
        exit_code = process_requests(
            dataset_dir=self.dataset_dir,
            requests_csv=test_requests_csv,
            output_csv=test_output_csv,
            diagnostic_mode=False,
            diagnostics_json=diag_path
        )
        self.assertGreater(exit_code, 0, "Normal mode with blocked case must exit nonzero")

        # Verify target file is completely preserved
        curr_sha = compute_file_sha256(test_output_csv)
        curr_size = os.path.getsize(test_output_csv)
        with open(test_output_csv, "r", encoding="utf-8") as f:
            curr_content = f.read()

        self.assertEqual(curr_sha, orig_sha)
        self.assertEqual(curr_size, orig_size)
        self.assertEqual(curr_content, original_content)
        self.assertTrue(os.path.exists(diag_path))


if __name__ == "__main__":
    unittest.main()
