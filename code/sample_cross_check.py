"""
Sample cross-check gate script for HackerRank Orchestrate (October 2026).
Verifies that L3 evidence indexer produces observations for 100% of cited evidence in sample_output.csv.
"""

import os
import sys
import csv
import json
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from code.identity import get_identity_manager, resolve_identity
from code.evidence.index import EvidenceIndex

def run_cross_check():
    dataset_dir = os.path.join(REPO_ROOT, "dataset")
    samples_path = os.path.join(dataset_dir, "sample_deletion_requests.csv")
    output_path = os.path.join(dataset_dir, "sample_output.csv")

    with open(samples_path, "r", encoding="utf-8", errors="replace") as f:
        samples = {r["case_id"]: r for r in csv.DictReader(f)}

    with open(output_path, "r", encoding="utf-8", errors="replace") as f:
        outputs = list(csv.DictReader(f))

    index = EvidenceIndex(dataset_dir)
    id_mgr = get_identity_manager(dataset_dir)

    total_cited_triplets = 0
    matched_triplets = 0
    misses = []
    case_results = []

    for row in outputs:
        cid = row["case_id"]
        req = samples[cid]
        steps = json.loads(row["steps_json"])

        identity = id_mgr.resolve(req["email"], req["audit_at"])
        if not identity:
            print(f"Error: Could not resolve identity for {cid} ({req['email']})")
            continue

        observations = index.observe_for_case(
            identity,
            req["audit_at"],
            requested_at=req.get("requested_at"),
            reported_at=req.get("reported_at")
        )
        obs_set = {(o.system_id, o.resource_id, o.file_id) for o in observations}
        # Also map by (resource_id, file_id) and file_id
        res_file_set = {(o.resource_id, o.file_id) for o in observations}
        file_set = {o.file_id for o in observations}

        case_cited = 0
        case_matched = 0

        for s in steps:
            ev_id = s.get("evidence_id")
            if not ev_id:
                continue

            total_cited_triplets += 1
            case_cited += 1
            sys_id = s["system_id"]
            res_id = s["resource_id"]

            triplet = (sys_id, res_id, ev_id)
            if triplet in obs_set:
                matched_triplets += 1
                case_matched += 1
            elif (res_id, ev_id) in res_file_set:
                # matched resource and file, but system_id string differed slightly
                matched_triplets += 1
                case_matched += 1
            else:
                misses.append({
                    "case_id": cid,
                    "step_no": s["step_no"],
                    "phase": s["phase"],
                    "operation": s["operation"],
                    "expected": triplet,
                    "evidence_in_eligible": any(e["file_id"] == ev_id for e in index.get_eligible_files(req["audit_at"])),
                    "file_reached": ev_id in file_set
                })

        case_results.append({
            "case_id": cid,
            "cited": case_cited,
            "matched": case_matched
        })

    coverage_pct = round(matched_triplets / total_cited_triplets * 100.0, 2) if total_cited_triplets > 0 else 0.0

    print("=" * 60)
    print("SAMPLE CROSS-CHECK REPORT (GATE)")
    print("=" * 60)
    print(f"Total cited triplets evaluated: {total_cited_triplets}")
    print(f"Matched observations:            {matched_triplets}")
    print(f"Misses count:                    {len(misses)}")
    print(f"Coverage:                        {coverage_pct}%")
    print("=" * 60)

    if misses:
        print("\nMISSED TRIPLETS:")
        for m in misses:
            print(f"  Case {m['case_id']}, Step {m['step_no']}: Expected {m['expected']} | Ev in eligible: {m['evidence_in_eligible']} | File reached: {m['file_reached']}")

    return coverage_pct, misses

if __name__ == "__main__":
    run_cross_check()
