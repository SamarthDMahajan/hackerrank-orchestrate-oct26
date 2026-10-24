"""
Evaluation Scorer for HackerRank Orchestrate (October 2026) - Ghost Data Still Exists.

Scores candidate output against ground-truth outputs (e.g., dataset/sample_output.csv).
Calculates:
1. Case-level deletion-status accuracy
2. Step-level Precision, Recall, and F1 (exact match on step tuple)
3. Field-level accuracy (phase, operation, state, system_id, resource_id, evidence_id)
4. Sequence accuracy (exact step sequence match)
"""

import os
import sys
import csv
import json
import argparse
from typing import Dict, List, Any, Tuple
from collections import defaultdict


def load_output(file_path: str) -> Dict[str, Dict[str, Any]]:
    cases = {}
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            cid = r["case_id"]
            status = r["deletion_status"]
            try:
                steps = json.loads(r["steps_json"])
            except Exception:
                steps = []
            cases[cid] = {
                "case_id": cid,
                "deletion_status": status,
                "steps": steps
            }
    return cases


def step_tuple(s: Dict[str, Any], include_evidence: bool = True) -> Tuple:
    if include_evidence:
        return (
            s.get("phase"),
            s.get("operation"),
            s.get("system_id"),
            s.get("resource_id"),
            s.get("state"),
            s.get("evidence_id", "")
        )
    return (
        s.get("phase"),
        s.get("operation"),
        s.get("system_id"),
        s.get("resource_id"),
        s.get("state")
    )


def score_predictions(candidate_path: str, ground_truth_path: str) -> Dict[str, Any]:
    cand = load_output(candidate_path)
    gt = load_output(ground_truth_path)

    common_cases = [cid for cid in gt if cid in cand]
    if not common_cases:
        return {
            "error": "No overlapping cases between candidate and ground truth.",
            "candidate_cases": len(cand),
            "ground_truth_cases": len(gt)
        }

    status_matches = 0
    sequence_matches = 0

    total_gt_steps = 0
    total_cand_steps = 0
    matched_steps = 0

    field_matches = defaultdict(int)
    field_totals = defaultdict(int)

    per_case_results = []

    for cid in sorted(common_cases):
        c_case = cand[cid]
        g_case = gt[cid]

        # 1. Status match
        s_match = (c_case["deletion_status"] == g_case["deletion_status"])
        if s_match:
            status_matches += 1

        c_steps = c_case["steps"]
        g_steps = g_case["steps"]

        total_cand_steps += len(c_steps)
        total_gt_steps += len(g_steps)

        c_tuples = [step_tuple(s, include_evidence=True) for s in c_steps]
        g_tuples = [step_tuple(s, include_evidence=True) for s in g_steps]

        # Sequence match
        seq_match = (c_tuples == g_tuples)
        if seq_match:
            sequence_matches += 1

        # Step-level set overlap
        g_set = list(g_tuples)
        c_set = list(c_tuples)
        case_step_matches = 0
        for ct in c_set:
            if ct in g_set:
                case_step_matches += 1
                g_set.remove(ct)
        matched_steps += case_step_matches

        # Field-level comparison on aligned steps (up to min length)
        for idx in range(min(len(c_steps), len(g_steps))):
            cs = c_steps[idx]
            gs = g_steps[idx]
            for field in ["phase", "operation", "system_id", "resource_id", "state", "evidence_id"]:
                field_totals[field] += 1
                if cs.get(field) == gs.get(field):
                    field_matches[field] += 1

        per_case_results.append({
            "case_id": cid,
            "status_match": s_match,
            "candidate_status": c_case["deletion_status"],
            "ground_truth_status": g_case["deletion_status"],
            "sequence_match": seq_match,
            "candidate_steps_count": len(c_steps),
            "ground_truth_steps_count": len(g_steps),
            "matched_steps_count": case_step_matches
        })

    num_cases = len(common_cases)
    status_accuracy = round(status_matches / num_cases * 100.0, 2)
    sequence_accuracy = round(sequence_matches / num_cases * 100.0, 2)

    precision = round(matched_steps / total_cand_steps * 100.0, 2) if total_cand_steps > 0 else 0.0
    recall = round(matched_steps / total_gt_steps * 100.0, 2) if total_gt_steps > 0 else 0.0
    f1 = round(2 * precision * recall / (precision + recall), 2) if (precision + recall) > 0 else 0.0

    field_accuracies = {}
    for fld, tot in field_totals.items():
        field_accuracies[fld] = round(field_matches[fld] / tot * 100.0, 2) if tot > 0 else 0.0

    return {
        "evaluated_cases": num_cases,
        "case_status_accuracy_pct": status_accuracy,
        "sequence_accuracy_pct": sequence_accuracy,
        "step_metrics": {
            "total_candidate_steps": total_cand_steps,
            "total_ground_truth_steps": total_gt_steps,
            "matched_steps": matched_steps,
            "precision_pct": precision,
            "recall_pct": recall,
            "f1_pct": f1
        },
        "field_accuracies_pct": field_accuracies,
        "per_case_results": per_case_results
    }


def main():
    parser = argparse.ArgumentParser(description="Score candidate predictions against ground truth")
    parser.add_argument("--candidate", required=True, help="Path to candidate output.csv")
    parser.add_argument("--truth", default=os.path.join("dataset", "sample_output.csv"), help="Path to ground truth sample_output.csv")
    args = parser.parse_args()

    results = score_predictions(args.candidate, args.truth)
    if "error" in results:
        print(f"Error: {results['error']}")
        sys.exit(1)

    print("=" * 60)
    print("EVALUATION SCORING SUMMARY")
    print("=" * 60)
    print(f"Cases Evaluated:           {results['evaluated_cases']}")
    print(f"Status Accuracy:           {results['case_status_accuracy_pct']}%")
    print(f"Sequence Accuracy:         {results['sequence_accuracy_pct']}%")
    print(f"Step Precision:            {results['step_metrics']['precision_pct']}%")
    print(f"Step Recall:               {results['step_metrics']['recall_pct']}%")
    print(f"Step F1 Score:             {results['step_metrics']['f1_pct']}%")
    print("\nField Accuracies (aligned steps):")
    for fld, acc in results["field_accuracies_pct"].items():
        print(f"  - {fld:15s}: {acc}%")
    print("=" * 60)


if __name__ == "__main__":
    main()
