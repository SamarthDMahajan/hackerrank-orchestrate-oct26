"""
Unit tests demonstrating that the independent comparator detects all errors.
Tests 7 distinct mutations on disposable in-memory/scratch copies without altering original files:
1. Flip one status
2. Change one evidence_id
3. Remove one step
4. Swap two distinct steps
5. Remove one case
6. Add an unexpected case
7. Duplicate one case
"""

import os
import csv
import json
import tempfile
import unittest

from code.evaluation.comparator import compare_outputs


class TestComparatorMutations(unittest.TestCase):
    def setUp(self):
        path = os.path.join("dataset", "sample_output.csv")
        if not os.path.exists(path):
            self.skipTest("dataset/sample_output.csv not present in isolated inference dataset")
        with open(path, "r", encoding="utf-8") as f:
            self.base_predictions = list(csv.DictReader(f))

    def write_temp_csv(self, rows: list) -> str:
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"])
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_baseline_passes(self):
        path = self.write_temp_csv(self.base_predictions)
        try:
            res = compare_outputs(path, "dataset/sample_output.csv")
            self.assertTrue(res.is_exact_match)
            self.assertEqual(res.total_candidate_cases, 32)
            self.assertEqual(res.total_expected_cases, 32)
            self.assertEqual(len(res.status_mismatches), 0)
            self.assertEqual(len(res.step_sequence_mismatches), 0)
        finally:
            os.remove(path)

    def test_mutation_1_flip_status(self):
        mutated = [dict(r) for r in self.base_predictions]
        self.assertEqual(mutated[0]["case_id"], "case_01")
        mutated[0]["deletion_status"] = "INCOMPLETE"
        path = self.write_temp_csv(mutated)
        try:
            res = compare_outputs(path, "dataset/sample_output.csv")
            self.assertFalse(res.is_exact_match)
            self.assertEqual(len(res.status_mismatches), 1)
            self.assertEqual(res.status_mismatches[0][0], "case_01")
        finally:
            os.remove(path)

    def test_mutation_2_change_evidence_id(self):
        mutated = [dict(r) for r in self.base_predictions]
        changed = False
        for r in mutated:
            steps = json.loads(r["steps_json"])
            for s in steps:
                if s.get("evidence_id"):
                    s["evidence_id"] = "evidence_999_fake"
                    r["steps_json"] = json.dumps(steps)
                    changed = True
                    break
            if changed:
                break
        self.assertTrue(changed)
        path = self.write_temp_csv(mutated)
        try:
            res = compare_outputs(path, "dataset/sample_output.csv")
            self.assertFalse(res.is_exact_match)
            self.assertGreaterEqual(res.field_mismatches["evidence_id"], 1)
        finally:
            os.remove(path)

    def test_mutation_3_remove_step(self):
        mutated = [dict(r) for r in self.base_predictions]
        self.assertEqual(mutated[2]["case_id"], "case_03")
        steps = json.loads(mutated[2]["steps_json"])
        self.assertGreater(len(steps), 1)
        steps.pop()
        mutated[2]["steps_json"] = json.dumps(steps)
        path = self.write_temp_csv(mutated)
        try:
            res = compare_outputs(path, "dataset/sample_output.csv")
            self.assertFalse(res.is_exact_match)
            self.assertEqual(res.total_candidate_steps, 192)
        finally:
            os.remove(path)

    def test_mutation_4_swap_distinct_steps(self):
        mutated = [dict(r) for r in self.base_predictions]
        self.assertEqual(mutated[10]["case_id"], "case_11")
        steps = json.loads(mutated[10]["steps_json"])
        self.assertGreaterEqual(len(steps), 2)
        steps[0], steps[1] = steps[1], steps[0]
        mutated[10]["steps_json"] = json.dumps(steps)
        path = self.write_temp_csv(mutated)
        try:
            res = compare_outputs(path, "dataset/sample_output.csv")
            self.assertFalse(res.is_exact_match)
            self.assertTrue(any(m["case_id"] == "case_11" for m in res.step_sequence_mismatches))
        finally:
            os.remove(path)

    def test_mutation_5_remove_case(self):
        mutated = [dict(r) for r in self.base_predictions]
        mutated = [r for r in mutated if r["case_id"] != "case_05"]
        self.assertEqual(len(mutated), 31)
        path = self.write_temp_csv(mutated)
        try:
            res = compare_outputs(path, "dataset/sample_output.csv")
            self.assertFalse(res.is_exact_match)
            self.assertIn("case_05", res.missing_cases)
        finally:
            os.remove(path)

    def test_mutation_6_add_unexpected_case(self):
        mutated = [dict(r) for r in self.base_predictions]
        mutated.append({
            "case_id": "case_99",
            "deletion_status": "COMPLETE",
            "steps_json": "[]"
        })
        self.assertEqual(len(mutated), 33)
        path = self.write_temp_csv(mutated)
        try:
            res = compare_outputs(path, "dataset/sample_output.csv")
            self.assertFalse(res.is_exact_match)
            self.assertIn("case_99", res.unexpected_cases)
        finally:
            os.remove(path)

    def test_mutation_7_duplicate_case(self):
        mutated = [dict(r) for r in self.base_predictions]
        mutated.append(dict(mutated[0]))
        self.assertEqual(len(mutated), 33)
        path = self.write_temp_csv(mutated)
        try:
            res = compare_outputs(path, "dataset/sample_output.csv")
            self.assertFalse(res.is_exact_match)
            self.assertIn("case_01", res.duplicate_cases)
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
