import os
import sys
import csv
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from code.identity import get_identity_manager, IdentitySet
from code.evidence.index import EvidenceIndex
from code.evidence.models import StateSignal, ResourceObservation


class TestEvidenceIndex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset_dir = os.path.join(REPO_ROOT, "dataset")
        cls.id_mgr = get_identity_manager(cls.dataset_dir)
        cls.index = EvidenceIndex(cls.dataset_dir)

    def test_temporal_cutoff_excludes_post_audit_evidence(self):
        # Pick a very early audit_at before any evidence was captured
        early_audit = "2020-01-01T00:00:00Z"
        files = self.index.get_eligible_files(early_audit)
        self.assertEqual(len(files), 0, "No evidence should be eligible prior to capture dates")

        # Pick a date after all evidence was captured
        future_audit = "2030-01-01T00:00:00Z"
        all_files = self.index.get_eligible_files(future_audit)
        self.assertEqual(len(all_files), len(self.index.manifest))

        # Check an intermediate cutoff
        timestamps = sorted([f["captured_at"] for f in self.index.manifest])
        mid_time = timestamps[len(timestamps) // 2]
        mid_files = self.index.get_eligible_files(mid_time)

        for f in mid_files:
            cap = f["captured_at"]
            self.assertLessEqual(cap, mid_time, f"Eligible file {f['file_id']} captured_at {cap} must be <= audit_at {mid_time}")

    def test_state_signal_validity(self):
        # Ensure StateSignal contains only the closed discovered enum values
        valid_signals = {
            "PRESENT", "ABSENT", "REDACTED", "ANONYMIZED",
            "ACTIVE", "DISABLED", "BLOCKED", "UNPARSED"
        }
        enum_values = {s.value for s in StateSignal}
        self.assertEqual(enum_values, valid_signals)

    def test_parsers_emit_valid_observations(self):
        # Read a real sample case
        with open(os.path.join(self.dataset_dir, "sample_deletion_requests.csv"), "r", encoding="utf-8", errors="replace") as f:
            first_req = next(csv.DictReader(f))

        ident = self.id_mgr.resolve(first_req["email"], first_req["audit_at"])
        self.assertIsNotNone(ident, "First sample request must resolve identity")

        obs = self.index.observe_for_case(
            ident,
            first_req["audit_at"],
            first_req["requested_at"],
            first_req["reported_at"]
        )
        self.assertIsInstance(obs, list)
        self.assertGreater(len(obs), 0, "Should generate observations for sample case")
        for o in obs:
            self.assertIsInstance(o, ResourceObservation)
            self.assertIn(o.state_signal, StateSignal)
            self.assertTrue(o.system_id, "system_id must not be empty")
            self.assertTrue(o.resource_id, "resource_id must not be empty")
            self.assertTrue(o.file_id, "file_id must not be empty")

    def test_pdf_parsing_stream_extraction(self):
        # Locate evidence_58 from manifest
        ev58_entry = None
        for r in self.index.manifest:
            if r["file_id"] == "evidence_58":
                ev58_entry = r
                break
        self.assertIsNotNone(ev58_entry, "evidence_58 must exist in manifest")

        pdf_path = os.path.join(self.dataset_dir, ev58_entry["file_path"])
        self.assertTrue(os.path.exists(pdf_path), f"{pdf_path} must exist")

        from code.evidence.pdf_parser import parse_pdf
        # Test with an identity matching evidence_58: case_07 subject
        # Look up case_07 in sample_deletion_requests
        case_07_req = None
        with open(os.path.join(self.dataset_dir, "sample_deletion_requests.csv"), "r", encoding="utf-8", errors="replace") as f:
            for r in csv.DictReader(f):
                if r["case_id"] == "case_07":
                    case_07_req = r
                    break
        self.assertIsNotNone(case_07_req)

        ident = self.id_mgr.resolve(case_07_req["email"], case_07_req["audit_at"])
        self.assertIsNotNone(ident)

        obs = parse_pdf(pdf_path, "evidence_58", ev58_entry["captured_at"], ident)
        self.assertGreaterEqual(len(obs), 1, "PDF parser should extract observation from evidence_58")
        self.assertEqual(obs[0].resource_id, "support_001")


if __name__ == "__main__":
    unittest.main()
