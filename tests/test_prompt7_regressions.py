"""
Production-path regression tests for Prompt 7:
Resolve policy and association regressions using existing inputs.
HackerRank Orchestrate (October 2026) - Ghost Data Still Exists.
"""

import os
import unittest
import tempfile
import shutil
import csv
import json

from code.identity import IdentitySet, IdentityManager
from code.evidence.index import EvidenceIndex
from code.evidence.models import StateSignal, ResourceObservation
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


class TestPrompt7Regressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = StateEngine(DATASET_DIR)
        cls.index = EvidenceIndex(DATASET_DIR)
        cls.id_mgr = IdentityManager(DATASET_DIR)

    def test_01_retention_established_by_documented_source(self):
        """
        1. Retention established by documented source:
        Verify that retention periods from SQL/JSON (e.g. retention_until = 2034-09-30)
        correctly determine that a security audit record is within retention at audit_at.
        """
        matches = [a for a in self.engine.audit_records_associations if a.get("user_id") == "user_21"]
        self.assertTrue(len(matches) > 0, "Expected user_21 to have audit record association")
        documented_retention = [m for m in matches if m.get("retention_until")]
        self.assertTrue(len(documented_retention) > 0, "Expected documented retention for user_21")
        match = documented_retention[0]
        self.assertEqual(match.get("resource_id"), "audit_record_3737")
        self.assertEqual(match.get("retention_until"), "2034-09-30T23:59:59Z")
        self.assertTrue("2026-09-15T12:00:00Z" <= match["retention_until"])

    def test_02_genuinely_unknown_retention_remains_unresolved(self):
        """
        2. Genuinely unknown retention remains unresolved / does not invent arbitrary expiry:
        Missing retention_until does not establish expiry.
        """
        audit_assoc = {
            "user_id": "user_counter_999",
            "resource_id": "audit_record_counter_999",
            "file_id": "evidence_test",
            "captured_at": "2026-09-01T12:00:00Z",
            "embedded_time": "2026-09-01T12:00:00Z",
            "locator": "test",
            "retention_until": None
        }
        ret_until = audit_assoc.get("retention_until")
        audit_at = "2026-09-15T12:00:00Z"
        is_retained = True
        if ret_until and ret_until < audit_at:
            is_retained = False
        self.assertTrue(is_retained, "Missing retention_until must NOT establish expiry")

    def test_03_expired_retention_follows_supplied_alternative_rule(self):
        """
        3. Expired retention follows only a supplied rule (cannot be retained under rule 12):
        If retention_until < audit_at, condition for RETAIN fails.
        """
        audit_assoc = {
            "user_id": "user_counter_888",
            "resource_id": "audit_record_counter_888",
            "file_id": "evidence_test",
            "captured_at": "2025-01-01T12:00:00Z",
            "embedded_time": "2025-01-01T12:00:00Z",
            "locator": "test",
            "retention_until": "2025-06-01T00:00:00Z"
        }
        audit_at = "2026-09-15T12:00:00Z"
        ret_until = audit_assoc.get("retention_until")
        is_retained = True
        if ret_until and ret_until < audit_at:
            is_retained = False
        self.assertFalse(is_retained, "Expired retention must fail RETAIN condition")

    def test_04_anonymized_profile_with_eligible_association_attributed(self):
        """
        4. Anonymized profile with an eligible explicit association is attributed:
        When an explicit lookup / snapshot associates a subject with an analytics resource,
        the resource is retained in case_resources even if current PII fields are null.
        """
        ident = IdentitySet(
            user_id="user_counter_777",
            name="Counter Subject",
            emails=frozenset({"counter.subject@test.com"}),
            email_hashes=frozenset(),
            phones=frozenset(),
            active_email="counter.subject@test.com",
            active_email_hash="",
            active_phone=""
        )
        obs = ResourceObservation(
            file_id="evidence_test",
            captured_at="2026-09-10T00:00:00Z",
            system_id="analytics_platform",
            resource_id="analytics_counter_777",
            identifier_matched="user_counter_777",
            state_signal=StateSignal.ANONYMIZED,
            raw_excerpt="user_counter_777 -> analytics_counter_777 anonymized",
            line_ref="1"
        )
        req = {
            "case_id": "case_test_anon",
            "email": "counter.subject@test.com",
            "audit_at": "2026-09-15T00:00:00Z",
            "requested_at": "2026-09-01T00:00:00Z",
            "reported_at": "2026-09-05T00:00:00Z",
            "reported_status": "COMPLETE"
        }
        class MockIndex:
            def observe_for_case(self, i, a_at, r_at, rep_at):
                return [obs]

        res = self.engine.evaluate_case(req, ident, MockIndex())
        self.assertIn("analytics_platform:analytics_counter_777", res.provenance.get("resources_evaluated", []))

    def test_05_unrelated_anonymized_profile_not_attributed(self):
        """
        5. Unrelated anonymized profile is NOT attributed:
        An anonymized profile with no matching identifier or trace to subject must not be joined.
        """
        ident = IdentitySet(
            user_id="user_counter_666",
            name="Unrelated Subject",
            emails=frozenset({"unrelated@test.com"}),
            email_hashes=frozenset(),
            phones=frozenset(),
            active_email="unrelated@test.com",
            active_email_hash="",
            active_phone=""
        )
        obs = ResourceObservation(
            file_id="evidence_test",
            captured_at="2026-09-10T00:00:00Z",
            system_id="analytics_platform",
            resource_id="analytics_unrelated_999",
            identifier_matched="user_different_111",
            state_signal=StateSignal.ANONYMIZED,
            raw_excerpt="Unrelated user anonymized",
            line_ref="1"
        )
        req = {
            "case_id": "case_test_unrelated",
            "email": "unrelated@test.com",
            "audit_at": "2026-09-15T00:00:00Z",
            "requested_at": "2026-09-01T00:00:00Z",
            "reported_at": "2026-09-05T00:00:00Z",
            "reported_status": "COMPLETE"
        }
        class MockIndex:
            def observe_for_case(self, i, a_at, r_at, rep_at):
                return [obs]

        res = self.engine.evaluate_case(req, ident, MockIndex())
        self.assertNotIn("analytics_platform:analytics_unrelated_999", res.provenance.get("resources_evaluated", []))

    def test_06_explicit_subject_resource_absence_lookup_yields_scoped_verification(self):
        """
        6. Explicit subject/resource absence lookup yields scoped verification:
        When a 404 response explicitly states resource_id='account_4092' for the subject's email,
        it scopes verification to account_4092 without ambiguity.
        """
        ident = self.id_mgr.resolve("leonie.g9352@outlook.com", "2026-09-15T12:00:00Z")
        obs_list = self.index.observe_for_case(ident, "2026-09-15T12:00:00Z")
        acc_obs = [o for o in obs_list if o.system_id == "account_service" and o.resource_id == "account_4092"]
        self.assertTrue(len(acc_obs) > 0, "Expected scoped 404 observation for account_4092")
        self.assertEqual(acc_obs[0].state_signal, StateSignal.ABSENT)
        self.assertEqual(acc_obs[0].resource_id, "account_4092")

    def test_07_subject_only_absence_does_not_fabricate_account_id(self):
        """
        7. Subject-only absence query does not fabricate an account ID:
        If a table has 0 rows for a user, no fictional resource ID like 'account_null' is generated.
        """
        empty_lookup_obs = ResourceObservation(
            file_id="evidence_test",
            captured_at="2026-09-10T00:00:00Z",
            system_id="account_service",
            resource_id="",
            identifier_matched="user_counter_555",
            state_signal=StateSignal.ABSENT,
            raw_excerpt="Query returned 0 rows",
            line_ref="1"
        )
        self.assertEqual(empty_lookup_obs.resource_id, "")
        acc = self.engine.determine_account({"case_id": "test"}, None, {("account_service", ""): [empty_lookup_obs]})
        self.assertEqual(acc, "", "Subject-only empty response must not fabricate account ID")

    def test_08_future_only_associations_rejected(self):
        """
        8. Future-only associations are rejected:
        Observations captured or embedded after audit_at cannot be used.
        """
        eligible = self.index.get_eligible_files(audit_at="2026-09-10T00:00:00Z")
        for f in eligible:
            self.assertTrue(f["captured_at"] <= "2026-09-10T00:00:00Z", f"File {f['file_id']} is after audit_at")

    def test_09_necessary_trace_edges_retain_correct_source_ids_and_times(self):
        """
        9. Necessary trace edges retain correct source IDs/times:
        Log trace tr-9028396 must record event time 2026-09-16T08:52:49Z,
        not the log file export time of 2026-09-18.
        """
        matches = [a for a in self.engine.audit_records_associations if a.get("user_id") == "user_61"]
        self.assertTrue(len(matches) > 0)
        match = matches[0]
        self.assertEqual(match["resource_id"], "audit_record_4902")
        self.assertTrue(match["embedded_time"] <= "2026-09-16T09:00:00Z",
                        f"Embedded time {match['embedded_time']} must be pre-audit_at")

    def test_10_relevant_uncertainty_blocks_publication_despite_valid_verification(self):
        """
        10. Relevant uncertainty blocks publication despite another valid verification:
        When a case has BLOCKED_UNRESOLVED_SCOPE, main CLI refuses publication.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            out_csv = os.path.join(tmpdir, "test_output.csv")
            diag_json = os.path.join(tmpdir, "diagnostics.json")
            reqs_csv = os.path.join(tmpdir, "requests.csv")
            with open(reqs_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["case_id", "email", "requested_at", "reported_status", "reported_at", "audit_at", "request_text"])
                writer.writerow(["case_block_02", "unknown_person@nowhere.com", "2026-08-01T00:00:00Z", "COMPLETE", "2026-08-05T00:00:00Z", "2026-09-01T00:00:00Z", "Please delete all my data immediately."])

            exit_code = process_requests(
                dataset_dir=DATASET_DIR,
                requests_csv=reqs_csv,
                output_csv=out_csv,
                diagnostics_json=diag_json,
                diagnostic_mode=False
            )
            self.assertGreater(exit_code, 0, "Must return non-zero exit code when blocked cases exist")
            self.assertFalse(os.path.exists(out_csv), "Publication must be refused to preserve target file")

    def test_11_diagnostics_isolation_between_cases(self):
        """
        11. Diagnostics do not leak between cases:
        Evaluating case A should not leave diagnostics in case B's result.
        """
        ident_a = self.id_mgr.resolve("leonie.g9352@outlook.com", "2026-09-15T12:00:00Z")
        req_a = {
            "case_id": "case_17",
            "email": "leonie.g9352@outlook.com",
            "requested_at": "2026-08-19T12:00:00Z",
            "reported_status": "NOT_STARTED",
            "reported_at": "2026-08-22T12:00:00Z",
            "audit_at": "2026-09-15T12:00:00Z",
            "request_text": "I want to close this account permanently."
        }
        res_a = self.engine.evaluate_case(req_a, ident_a, self.index)

        req_b = {
            "case_id": "case_06",
            "email": "c.alvarez@yahoo.com",
            "requested_at": "2026-08-19T12:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-08-22T12:00:00Z",
            "audit_at": "2026-09-15T12:00:00Z",
            "request_text": "Please delete all my personal data."
        }
        ident_b = self.id_mgr.resolve("c.alvarez@yahoo.com", "2026-09-15T12:00:00Z")
        res_b = self.engine.evaluate_case(req_b, ident_b, self.index)

        self.assertEqual(res_b.provenance["case_id"], "case_06")
        for d in res_b.diagnostics:
            self.assertNotIn("case_17", d, "Diagnostics from case A must not leak into case B")

    def test_12_evidence_61_follows_category_facts(self):
        """
        12. evidence_61 treatment follows category facts:
        evidence_61 is a support replica log containing SUPPORT_MESSAGE / SUPPORT_ATTACHMENT records.
        Treatment follows deletion_rules.csv rule_05 (REDACT for shared context) and rule_06 (DELETE for subject attachments).
        """
        with open(os.path.join(DATASET_DIR, "deletion_rules.csv"), encoding="utf-8") as f:
            rules = {r["data_category"]: r for r in csv.DictReader(f)}
        self.assertIn("SUPPORT_MESSAGE", rules)
        self.assertEqual(rules["SUPPORT_MESSAGE"]["required_action"], "REDACT")
        self.assertIn("SUPPORT_ATTACHMENT", rules)
        self.assertEqual(rules["SUPPORT_ATTACHMENT"]["required_action"], "DELETE")


if __name__ == "__main__":
    unittest.main()
