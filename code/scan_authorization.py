"""
Request-only scan for L4 authorization on the 518 evaluation requests.
Produces evaluation/authorization_manifest.csv with:
- case_id
- original_request_text
- proposed_authorization
- rule_model_provenance
- supporting_spans
- unresolved_reason
- review_status
"""

import os
import sys
import csv
import json

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from code.intent import classify_intent, AuthorizationOutcome

REQ_FILE = os.path.join(REPO_ROOT, "dataset", "deletion_requests.csv")
EVAL_DIR = os.path.join(REPO_ROOT, "evaluation")
MANIFEST_OUT = os.path.join(EVAL_DIR, "authorization_manifest.csv")


def run_request_scan():
    os.makedirs(EVAL_DIR, exist_ok=True)
    
    with open(REQ_FILE, "r", encoding="utf-8", errors="replace") as f:
        reader = list(csv.DictReader(f))

    manifest_rows = []
    counts = {
        AuthorizationOutcome.DELETE_AUTHORIZED.value: 0,
        AuthorizationOutcome.NON_DELETION.value: 0,
        AuthorizationOutcome.UNRESOLVED.value: 0,
    }

    unresolved_cases = []

    for row in reader:
        cid = row["case_id"]
        text = row["request_text"]
        
        # Only request_text is passed to the classifier
        intent_res = classify_intent(text, case_id=cid)
        outcome = intent_res.outcome.value
        counts[outcome] += 1

        unresolved_reason = ""
        if intent_res.outcome == AuthorizationOutcome.UNRESOLVED:
            unresolved_reason = intent_res.rationale
            unresolved_cases.append((cid, text, intent_res.matched_rule, intent_res.rationale))

        manifest_rows.append({
            "case_id": cid,
            "original_request_text": text,
            "proposed_authorization": outcome,
            "rule_model_provenance": f"{intent_res.confidence_category}:{intent_res.matched_rule}",
            "supporting_spans": json.dumps(intent_res.supporting_spans, ensure_ascii=False),
            "unresolved_reason": unresolved_reason,
            "review_status": "PROPOSED_AUTOMATED"
        })

    with open(MANIFEST_OUT, "w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "case_id",
            "original_request_text",
            "proposed_authorization",
            "rule_model_provenance",
            "supporting_spans",
            "unresolved_reason",
            "review_status"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(manifest_rows)

    print("=== REQUEST-ONLY AUTHORIZATION SCAN RESULTS ===")
    print(f"Total requests scanned: {len(reader)}")
    for outcome, count in counts.items():
        pct = (count / len(reader)) * 100
        print(f"  {outcome}: {count} ({pct:.2f}%)")
    print(f"\nWrote review manifest to {MANIFEST_OUT}")

    if unresolved_cases:
        print(f"\nUnresolved / Disputed Requests ({len(unresolved_cases)}):")
        for cid, txt, rule, rat in unresolved_cases:
            print(f"  [{cid}] Rule: {rule} | Rationale: {rat}\n    Text: {txt}")
    else:
        print("\nNo unresolved requests found. All 518 requests resolved deterministically.")


if __name__ == "__main__":
    run_request_scan()
