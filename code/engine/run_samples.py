import os
import sys
import csv
import json

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from code.identity import get_identity_manager
from code.evidence.index import EvidenceIndex
from code.engine.state import StateEngine
from code.engine.assemble import serialize_steps
from code.evaluation.scorer import score_predictions

import argparse

parser = argparse.ArgumentParser(description="Run deletion audit engine on sample requests.")
parser.add_argument("--dataset-dir", default=os.path.join(REPO_ROOT, "dataset"), help="Path to dataset directory")
parser.add_argument("--output-csv", default=os.path.join(REPO_ROOT, "sample_pred.csv"), help="Output predictions path")
parser.add_argument("--truth-csv", default=None, help="Optional ground truth CSV path")
args = parser.parse_args()

DATASET_DIR = args.dataset_dir
out_path = args.output_csv
id_mgr = get_identity_manager(DATASET_DIR)
index = EvidenceIndex(DATASET_DIR)
engine = StateEngine(DATASET_DIR)

from code.intent import classify_intent, AuthorizationOutcome

sample_req_path = os.path.join(DATASET_DIR, "sample_deletion_requests.csv")
with open(sample_req_path, "r", encoding="utf-8", errors="replace") as f:
    sample_requests = list(csv.DictReader(f))

pred_rows = []
for req in sample_requests:
    cid = req["case_id"]
    email = req["email"]
    audit_at = req["audit_at"]
    req_text = req.get("request_text", "")
    
    # 1. L4 Request Authorization
    auth_res = classify_intent(req_text, case_id=cid)
    if auth_res.outcome == AuthorizationOutcome.NON_DELETION:
        status = "NOT_APPLICABLE"
        steps = []
    elif auth_res.outcome == AuthorizationOutcome.UNRESOLVED:
        raise RuntimeError(f"Case {cid} has unresolved authorization: {auth_res.rationale}")
    elif auth_res.outcome == AuthorizationOutcome.DELETE_AUTHORIZED:
        identity = id_mgr.resolve(email, audit_at)
        if not identity:
            print(f"Warning: could not resolve identity for {cid} ({email})")
            status, steps = "INCOMPLETE", []
        else:
            status, steps = engine.evaluate_case(req, identity, index)
    else:
        raise ValueError(f"Unexpected authorization outcome: {auth_res.outcome}")

    pred_rows.append({
        "case_id": cid,
        "deletion_status": status,
        "steps_json": serialize_steps(steps)
    })

# Write predictions
with open(out_path, "w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"])
    writer.writeheader()
    writer.writerows(pred_rows)

print(f"Wrote {len(pred_rows)} predictions to {out_path}")

# Evaluate only if truth CSV is explicitly provided as a separate argument
truth_path = args.truth_csv
if truth_path and os.path.exists(truth_path):
    results = score_predictions(out_path, truth_path)
    sample_truth = {r["case_id"]: (r["deletion_status"], json.loads(r["steps_json"])) for r in csv.DictReader(open(truth_path, "r", encoding="utf-8", errors="replace"))}
    print("\n--- EVALUATION SUMMARY ---")
    print(f"Status Accuracy: {results['case_status_accuracy_pct']}%")
    print(f"Sequence Accuracy: {results['sequence_accuracy_pct']}%")
    print(f"Step Precision: {results['step_metrics']['precision_pct']}%")
    print(f"Step Recall: {results['step_metrics']['recall_pct']}%")
    print(f"Step F1: {results['step_metrics']['f1_pct']}%")
    print("\nField Accuracies:")
    for k, v in results['field_accuracies_pct'].items():
        print(f"  {k}: {v}%")

    print("\n--- PER-CASE RESULTS ---")
    for pc in results['per_case_results']:
        cid = pc['case_id']
        s_match = pc['status_match']
        seq_match = pc['sequence_match']
        gt_s, gt_steps = sample_truth[cid]
        pred_row = next(r for r in pred_rows if r['case_id'] == cid)
        pred_steps = json.loads(pred_row['steps_json'])
        
        match_str = "MATCH" if (s_match and seq_match) else "MISMATCH"
        print(f"\n[{match_str}] Case: {cid} | Status: {pred_row['deletion_status']} (Expected: {gt_s}) | Steps: {len(pred_steps)} (Expected: {len(gt_steps)})")
        if not (s_match and seq_match):
            print("  Predicted Steps:")
            for s in pred_steps:
                print(f"    {s.get('phase')} | {s.get('operation')} | {s.get('system_id')} | {s.get('resource_id')} | {s.get('state')} | {s.get('evidence_id')}")
            print("  Expected Steps:")
            for s in gt_steps:
                print(f"    {s.get('phase')} | {s.get('operation')} | {s.get('system_id')} | {s.get('resource_id')} | {s.get('state')} | {s.get('evidence_id')}")
else:
    print(f"\nTruth file not found at {truth_path}. Skipping evaluation (inference only).")
