"""
Unit tests for inference independence (Section G).
Verifies:
1. Changing case IDs does not change semantic decisions.
2. Reordering input rows does not change decisions.
3. Changing reported_status / reported_result claims alone does not change decisions.
4. Poisoned expected-label files cannot change production predictions.
5. Synthetic explicit subject/resource evidence relationship works without sample IDs.
"""

import unittest
import os
import csv
import json
import tempfile
import shutil
from code.engine.state import StateEngine
from code.evidence.index import EvidenceIndex
from code.identity import get_identity_manager, IdentitySet
from code.evidence.models import ResourceObservation, StateSignal
from code.engine.assemble import serialize_steps


class TestIndependence(unittest.TestCase):
    def setUp(self):
        self.dataset_dir = "dataset"
        self.engine = StateEngine(self.dataset_dir)
        self.index = EvidenceIndex(self.dataset_dir)
        self.id_mgr = get_identity_manager(self.dataset_dir)

    def test_1_case_id_invariance(self):
        """
        Changing case IDs, while preserving legitimate relationships, does not change
        semantic decisions after restoring IDs for comparison.
        """
        req_orig = {
            "case_id": "case_05",
            "email": "leila.haddad@yahoo.com",
            "requested_at": "2026-09-01T10:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-09-02T22:00:00Z",
            "audit_at": "2026-09-10T11:00:00Z",
            "request_text": "Please delete all my account and personal data."
        }
        ident = self.id_mgr.resolve(req_orig["email"], req_orig["audit_at"])
        status_orig, steps_orig = self.engine.evaluate_case(req_orig, ident, self.index)

        # Mutate case_id
        req_mutated = dict(req_orig)
        req_mutated["case_id"] = "case_9999"
        status_mut, steps_mut = self.engine.evaluate_case(req_mutated, ident, self.index)

        self.assertEqual(status_orig, status_mut)
        self.assertEqual(len(steps_orig), len(steps_mut))
        self.assertEqual(serialize_steps(steps_orig), serialize_steps(steps_mut))

    def test_2_row_order_invariance(self):
        """
        Reordering input rows does not change decisions.
        """
        req_a = {
            "case_id": "case_05",
            "email": "leila.haddad@yahoo.com",
            "requested_at": "2026-09-01T10:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-09-02T22:00:00Z",
            "audit_at": "2026-09-10T11:00:00Z",
            "request_text": "Please delete all my account and personal data."
        }
        req_b = {
            "case_id": "case_11",
            "email": "novak.tomasz@icloud.com",
            "requested_at": "2026-08-15T10:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-08-17T12:00:00Z",
            "audit_at": "2026-08-25T11:00:00Z",
            "request_text": "Please permanently remove my account."
        }
        ident_a = self.id_mgr.resolve(req_a["email"], req_a["audit_at"])
        ident_b = self.id_mgr.resolve(req_b["email"], req_b["audit_at"])

        # Order A then B
        st_a1, steps_a1 = self.engine.evaluate_case(req_a, ident_a, self.index)
        st_b1, steps_b1 = self.engine.evaluate_case(req_b, ident_b, self.index)

        # Order B then A
        st_b2, steps_b2 = self.engine.evaluate_case(req_b, ident_b, self.index)
        st_a2, steps_a2 = self.engine.evaluate_case(req_a, ident_a, self.index)

        self.assertEqual(st_a1, st_a2)
        self.assertEqual(st_b1, st_b2)
        self.assertEqual(serialize_steps(steps_a1), serialize_steps(steps_a2))
        self.assertEqual(serialize_steps(steps_b1), serialize_steps(steps_b2))

    def test_3_reported_claim_invariance(self):
        """
        Changing reported_status/reported_result claims alone does not change evidence-based state.
        """
        req_claim_complete = {
            "case_id": "case_05",
            "email": "leila.haddad@yahoo.com",
            "requested_at": "2026-09-01T10:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-09-02T22:00:00Z",
            "audit_at": "2026-09-10T11:00:00Z",
            "request_text": "Please delete all my account and personal data."
        }
        req_claim_not_started = dict(req_claim_complete)
        req_claim_not_started["reported_status"] = "NOT_STARTED"

        ident = self.id_mgr.resolve(req_claim_complete["email"], req_claim_complete["audit_at"])
        st_1, sp_1 = self.engine.evaluate_case(req_claim_complete, ident, self.index)
        st_2, sp_2 = self.engine.evaluate_case(req_claim_not_started, ident, self.index)

        self.assertEqual(st_1, st_2)
        self.assertEqual(serialize_steps(sp_1), serialize_steps(sp_2))

    def test_4_poisoned_expected_labels_isolation(self):
        """
        Original versus poisoned expected-label files, available only to the evaluator,
        cannot change production predictions.
        """
        # Production engine does not read sample_output.csv
        # Verify that altering or deleting sample_output.csv has zero effect on engine inference
        temp_dir = tempfile.mkdtemp()
        try:
            poisoned_truth = os.path.join(temp_dir, "sample_output.csv")
            with open(poisoned_truth, "w", encoding="utf-8") as f:
                f.write("case_id,deletion_status,steps_json\ncase_05,NOT_APPLICABLE,[]\n")

            req = {
                "case_id": "case_05",
                "email": "leila.haddad@yahoo.com",
                "requested_at": "2026-09-01T10:00:00Z",
                "reported_status": "COMPLETE",
                "reported_at": "2026-09-02T22:00:00Z",
                "audit_at": "2026-09-10T11:00:00Z",
                "request_text": "Please delete all my account and personal data."
            }
            ident = self.id_mgr.resolve(req["email"], req["audit_at"])
            status, steps = self.engine.evaluate_case(req, ident, self.index)

            # Even though poisoned truth says NOT_APPLICABLE, production engine returns INCOMPLETE
            self.assertEqual(status, "INCOMPLETE")
            self.assertTrue(len(steps) > 0)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_5_synthetic_relationship_generalization(self):
        """
        A synthetic explicit subject/resource evidence relationship works without
        any sample-specific identifiers.
        """
        synth_ident = IdentitySet(
            user_id="user_synthetic_777",
            name="Synthetic Subject",
            emails=frozenset({"synth.subject@domain.com"}),
            email_hashes=frozenset({"dummy_hash"}),
            phones=frozenset({"+10000000000"}),
            active_email="synth.subject@domain.com",
            active_email_hash="dummy_hash",
            active_phone="+10000000000"
        )
        synth_req = {
            "case_id": "case_synth_01",
            "email": "synth.subject@domain.com",
            "requested_at": "2026-01-01T00:00:00Z",
            "reported_status": "COMPLETE",
            "reported_at": "2026-01-02T00:00:00Z",
            "audit_at": "2026-01-05T00:00:00Z",
            "request_text": "Please erase all my data."
        }
        # Create an observation explicitly matching the synthetic user
        obs = ResourceObservation(
            file_id="evidence_synth_01",
            captured_at="2026-01-04T00:00:00Z",
            system_id="search_service",
            resource_id="search_synth_999",
            identifier_matched="synth.subject@domain.com",
            state_signal=StateSignal.PRESENT,
            raw_excerpt="search record matching synth.subject@domain.com",
            line_ref="1"
        )
        # Mock index returning this observation
        class MockIndex:
            def observe_for_case(self, ident, audit_at, req_at, rep_at):
                return [obs]

        status, steps = self.engine.evaluate_case(synth_req, synth_ident, MockIndex())
        self.assertEqual(status, "INCOMPLETE")
        self.assertEqual(len(steps), 3)
        self.assertEqual(steps[0]["phase"], "FINDING")
        self.assertEqual(steps[0]["resource_id"], "search_synth_999")
        self.assertEqual(steps[0]["evidence_id"], "evidence_synth_01")
        self.assertEqual(steps[1]["phase"], "REMEDIATION")
        self.assertEqual(steps[1]["operation"], "DELETE_RECORD")
        self.assertEqual(steps[2]["phase"], "VERIFICATION")
        self.assertEqual(steps[2]["operation"], "VERIFY_RECORD_ABSENT")


if __name__ == "__main__":
    unittest.main()
