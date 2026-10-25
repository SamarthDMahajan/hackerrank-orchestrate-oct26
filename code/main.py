"""
Main pipeline entrypoint for HackerRank Orchestrate (October 2026)
Ghost Data Still Exists.

Pipeline Order:
1. L4 Request Authorization (code/intent.py):
   - NON_DELETION -> NOT_APPLICABLE with steps_json=[]
   - DELETE_AUTHORIZED -> proceed to L2/L3/L5 pipeline
   - UNRESOLVED -> block and report explicit diagnostic
2. L2 Identity Resolution (code/identity.py): Reconstruct current and historical identifiers up to audit_at.
3. L3 Evidence Observation (code/evidence/index.py): Observe candidate resources up to audit_at.
4. L5 State Engine (code/engine/state.py): Apply deletion policy, detect findings, build remediation, and state verification.
5. L6 Assembly & Serialization (code/engine/assemble.py): Format steps consecutively into valid JSON.
"""

from __future__ import annotations
import os
import sys
import csv
import json
import argparse
from typing import List, Dict, Any, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from code.contracts import (
    CaseEvaluationResult,
    VerdictCertainty,
    PlanCompleteness,
    DeletionStatus,
    Step,
)
from code.intent import classify_intent, AuthorizationOutcome
from code.identity import get_identity_manager
from code.evidence.index import EvidenceIndex
from code.engine.state import StateEngine
from code.engine.assemble import serialize_steps


def process_requests(
    dataset_dir: str,
    requests_csv: str,
    output_csv: str,
    diagnostic_mode: bool = False,
    diagnostics_json: Optional[str] = None
) -> int:
    id_mgr = get_identity_manager(dataset_dir)
    index = EvidenceIndex(dataset_dir)
    engine = StateEngine(dataset_dir)

    with open(requests_csv, "r", encoding="utf-8", errors="replace") as f:
        reader = list(csv.DictReader(f))

    all_case_results: List[CaseEvaluationResult] = []
    diagnostics_records: List[Dict[str, Any]] = []

    for req in reader:
        cid = req.get("case_id", "")
        email = req.get("email", "")
        audit_at = req.get("audit_at", "")
        req_text = req.get("request_text", "")

        # 1. L4 Request Authorization
        auth_res = classify_intent(req_text, case_id=cid)

        if auth_res.outcome == AuthorizationOutcome.NON_DELETION:
            case_res = CaseEvaluationResult(
                case_id=cid,
                is_deletion=False,
                status=DeletionStatus.NOT_APPLICABLE,
                verdict_certainty=VerdictCertainty.CONFIRMED,
                plan_completeness=PlanCompleteness.NOT_APPLICABLE,
                steps=[],
                diagnostics=[],
                provenance={"authorization": auth_res.rationale}
            )
        elif auth_res.outcome == AuthorizationOutcome.UNRESOLVED:
            case_res = CaseEvaluationResult(
                case_id=cid,
                is_deletion=False,
                status=None,
                verdict_certainty=VerdictCertainty.BLOCKED_UNRESOLVED_SCOPE,
                plan_completeness=PlanCompleteness.INCOMPLETE_SCOPE,
                steps=[],
                diagnostics=[f"Case {cid} authorization is UNRESOLVED: {auth_res.rationale}"],
                provenance={"authorization": auth_res.rationale}
            )
        elif auth_res.outcome == AuthorizationOutcome.DELETE_AUTHORIZED:
            identity = id_mgr.resolve(email, audit_at)
            if not identity:
                case_res = CaseEvaluationResult(
                    case_id=cid,
                    is_deletion=True,
                    status=None,
                    verdict_certainty=VerdictCertainty.BLOCKED_ASSOCIATION_GAP,
                    plan_completeness=PlanCompleteness.INCOMPLETE_SCOPE,
                    steps=[],
                    diagnostics=[f"Could not resolve identity for {cid} ({email}) at audit_at {audit_at}"],
                    provenance={"email": email, "audit_at": audit_at}
                )
            else:
                case_res = engine.evaluate_case(req, identity, index)
        else:
            raise ValueError(f"Unknown authorization outcome: {auth_res.outcome}")

        all_case_results.append(case_res)
        diagnostics_records.append({
            "case_id": cid,
            "is_deletion": case_res.is_deletion,
            "verdict_certainty": case_res.verdict_certainty.value,
            "plan_completeness": case_res.plan_completeness.value,
            "status": case_res.status.value if case_res.status else None,
            "steps_count": len(case_res.steps),
            "diagnostics": case_res.diagnostics,
            "provenance": case_res.provenance
        })

    # Save detailed diagnostics JSON
    diag_path = diagnostics_json or os.path.join(REPO_ROOT, "evaluation", "all_case_diagnostics.json")
    os.makedirs(os.path.dirname(diag_path), exist_ok=True)
    with open(diag_path, "w", encoding="utf-8") as f:
        json.dump(diagnostics_records, f, indent=2)
    print(f"Saved all-case diagnostics ({len(diagnostics_records)} records) to {diag_path}")

    blocked_cases = [r for r in all_case_results if r.is_blocked()]

    if not diagnostic_mode:
        if blocked_cases:
            print(f"\nCRITICAL: {len(blocked_cases)}/{len(all_case_results)} cases have unresolved decision/plan blockers.")
            for b in blocked_cases[:10]:
                print(f"  - {b.case_id}: {b.verdict_certainty.value} -> {'; '.join(b.diagnostics)}")
            if len(blocked_cases) > 10:
                print(f"  ... and {len(blocked_cases) - 10} more. Refusing to publish unverified output.")
            print(f"Final output publication refused to preserve diagnostic integrity. Target {output_csv} NOT modified.")
            return len(blocked_cases)

        # All rows confirmed and eligible for publication
        pred_rows = []
        for r in all_case_results:
            raw_steps = [s.model_dump() for s in r.steps]
            pred_rows.append({
                "case_id": r.case_id,
                "deletion_status": r.status.value if r.status else "",
                "steps_json": serialize_steps(raw_steps)
            })

        with open(output_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"])
            writer.writeheader()
            writer.writerows(pred_rows)

        print(f"Wrote {len(pred_rows)} validated predictions to {output_csv}")
        return 0

    else:
        # Diagnostic sample mode: output diagnostics and candidate predictions without certifying production submission
        print(f"\nDIAGNOSTIC MODE: Processed {len(all_case_results)} requests.")
        print(f"  Confirmed cases: {len(all_case_results) - len(blocked_cases)}")
        print(f"  Blocked cases:   {len(blocked_cases)}")

        diag_pred_rows = []
        for r in all_case_results:
            raw_steps = [s.model_dump() for s in r.steps]
            diag_pred_rows.append({
                "case_id": r.case_id,
                "deletion_status": r.status.value if r.status else "BLOCKED",
                "steps_json": serialize_steps(raw_steps) if r.status else "[]"
            })

        if output_csv:
            os.makedirs(os.path.dirname(os.path.abspath(output_csv)), exist_ok=True)
            with open(output_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"])
                writer.writeheader()
                writer.writerows(diag_pred_rows)
            print(f"Wrote {len(diag_pred_rows)} diagnostic predictions to {output_csv}")

        return len(blocked_cases)


def main():
    parser = argparse.ArgumentParser(description="Ghost Data Still Exists Deletion Audit Agent")
    parser.add_argument("--dataset-dir", default=os.path.join(REPO_ROOT, "dataset"), help="Path to dataset directory")
    parser.add_argument("--requests-csv", default=None, help="Path to requests CSV (defaults to dataset/deletion_requests.csv if present, else sample_deletion_requests.csv)")
    parser.add_argument("--output-csv", default=os.path.join(REPO_ROOT, "output.csv"), help="Path to output CSV")
    parser.add_argument("--diagnostic-mode", action="store_true", help="Enable diagnostic mode to record all-case diagnostics without failing on blockers")
    parser.add_argument("--diagnostics-json", default=None, help="Path to write diagnostics JSON")
    args = parser.parse_args()

    default_requests = os.path.join(args.dataset_dir, "deletion_requests.csv")
    if not os.path.exists(default_requests):
        default_requests = os.path.join(args.dataset_dir, "sample_deletion_requests.csv")
    requests_file = args.requests_csv or default_requests
    blocked_count = process_requests(
        dataset_dir=args.dataset_dir,
        requests_csv=requests_file,
        output_csv=args.output_csv,
        diagnostic_mode=args.diagnostic_mode,
        diagnostics_json=args.diagnostics_json
    )
    if blocked_count > 0 and not args.diagnostic_mode:
        sys.exit(1)


if __name__ == "__main__":
    main()
