"""
Output Validation Script for HackerRank Orchestrate (October 2026)
Ghost Data Still Exists

Validates an output.csv against the exact schema and invariants:
- Header must be exactly: case_id,deletion_status,steps_json
- Row count matches requests file exactly
- Sorted ascending by case_id
- deletion_status in {COMPLETE, INCOMPLETE, NOT_APPLICABLE}
- steps_json is a valid JSON array
- For NOT_APPLICABLE: steps_json == []
- Consecutive step_no starting from 1
- Phase order: FINDING -> REMEDIATION -> VERIFICATION
- Operation order within phase per problem_statement.md
- Tie-breaking: system_id ascending, resource_id ascending
- Operation to state mapping validation
- Evidence ID constraints (empty vs non-empty)
- Temporal constraint: cited evidence must have timestamp <= case audit_at
- Exits with code 0 on success, code 1 on failure
"""

import os
import sys
import csv
import json
import argparse
from datetime import datetime
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(REPO_ROOT, "dataset")

# Expected operation -> state mapping
ALLOWED_OP_STATE = {
    # Findings
    "REPORT_REMAINING_RECORD": "PRESENT",
    "REPORT_EXPOSED_PII": "PRESENT",
    "REPORT_ACTIVE_DATA_FLOW": "ACTIVE",
    "REPORT_RESTORE_RISK": "ACTIVE",
    # Remediation
    "DISABLE_DATA_FLOW": "DISABLED",
    "BLOCK_RESTORE": "BLOCKED",
    "DELETE_RECORD": "ABSENT",
    "REDACT_RECORD": "REDACTED",
    "ANONYMIZE_RECORD": "ANONYMIZED",
    # Verification
    "VERIFY_RECORD_ABSENT": "ABSENT",
    "VERIFY_RECORD_PRESENT": "PRESENT",
    "VERIFY_RECORD_REDACTED": "REDACTED",
    "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED",
    "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
    "VERIFY_RESTORE_BLOCKED": "BLOCKED"
}

PHASE_ORDER = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}

OPERATION_ORDER = {
    "FINDING": {
        "REPORT_REMAINING_RECORD": 0,
        "REPORT_EXPOSED_PII": 1,
        "REPORT_ACTIVE_DATA_FLOW": 2,
        "REPORT_RESTORE_RISK": 3
    },
    "REMEDIATION": {
        "DISABLE_DATA_FLOW": 0,
        "BLOCK_RESTORE": 1,
        "DELETE_RECORD": 2,
        "REDACT_RECORD": 3,
        "ANONYMIZE_RECORD": 4
    },
    "VERIFICATION": {
        "VERIFY_RECORD_ABSENT": 0,
        "VERIFY_RECORD_PRESENT": 1,
        "VERIFY_RECORD_REDACTED": 2,
        "VERIFY_RECORD_ANONYMIZED": 3,
        "VERIFY_DATA_FLOW_DISABLED": 4,
        "VERIFY_RESTORE_BLOCKED": 5
    }
}


def load_evidence_timestamps():
    timestamps = {}
    # 1. evidence_files.csv
    ev_path = os.path.join(DATASET_DIR, "evidence_files.csv")
    if os.path.exists(ev_path):
        with open(ev_path, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                timestamps[r["file_id"]] = r["captured_at"]
    # 2. system_activity.csv
    act_path = os.path.join(DATASET_DIR, "system_activity.csv")
    if os.path.exists(act_path):
        with open(act_path, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                timestamps[r["activity_id"]] = r["event_time"]
    # 3. user_audit_log.csv
    aud_path = os.path.join(DATASET_DIR, "user_audit_log.csv")
    if os.path.exists(aud_path):
        with open(aud_path, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                timestamps[r["audit_id"]] = r["event_time"]
    return timestamps


def validate_file(output_path, requests_path):
    errors = []
    print(f"Validating output file: {output_path}")
    print(f"Against requests file: {requests_path}")

    if not os.path.exists(output_path):
        print(f"ERROR: Output file does not exist: {output_path}")
        return False, [f"Output file does not exist: {output_path}"]

    if not os.path.exists(requests_path):
        print(f"ERROR: Requests file does not exist: {requests_path}")
        return False, [f"Requests file does not exist: {requests_path}"]

    # Load requests
    with open(requests_path, "r", encoding="utf-8") as f:
        req_rows = list(csv.DictReader(f))
    expected_case_ids = [r["case_id"] for r in req_rows]
    case_audit_map = {r["case_id"]: r["audit_at"] for r in req_rows}
    expected_count = len(expected_case_ids)

    # Load evidence timestamps
    evidence_timestamps = load_evidence_timestamps()

    # Load output
    with open(output_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header != ["case_id", "deletion_status", "steps_json"]:
            errors.append(f"Header mismatch. Expected ['case_id', 'deletion_status', 'steps_json'], got {header}")
        output_rows = list(reader)

    if len(output_rows) != expected_count:
        errors.append(f"Row count mismatch: expected {expected_count} rows, found {len(output_rows)} rows")

    prev_case_id = None
    for row_idx, r in enumerate(output_rows):
        line_num = row_idx + 2
        if len(r) != 3:
            errors.append(f"Line {line_num}: Expected 3 columns, found {len(r)}")
            continue

        case_id, deletion_status, steps_json_str = r[0], r[1], r[2]

        # Case ID check
        if row_idx < len(expected_case_ids):
            if case_id != expected_case_ids[row_idx]:
                errors.append(f"Line {line_num}: Expected case_id '{expected_case_ids[row_idx]}', found '{case_id}'")

        if prev_case_id is not None and case_id < prev_case_id:
            errors.append(f"Line {line_num}: Case IDs not sorted ascending ('{case_id}' after '{prev_case_id}')")
        prev_case_id = case_id

        # Status check
        if deletion_status not in ["COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"]:
            errors.append(f"Line {line_num}: Invalid deletion_status '{deletion_status}'")

        # Parse steps_json
        try:
            steps = json.loads(steps_json_str)
        except Exception as e:
            errors.append(f"Line {line_num}: steps_json is not valid JSON: {e}")
            continue

        if not isinstance(steps, list):
            errors.append(f"Line {line_num}: steps_json must be a JSON array, got {type(steps).__name__}")
            continue

        if deletion_status == "NOT_APPLICABLE":
            if len(steps) != 0:
                errors.append(f"Line {line_num}: NOT_APPLICABLE must have empty steps_json '[]', found {len(steps)} steps")
            continue

        if len(steps) == 0:
            errors.append(f"Line {line_num}: {deletion_status} case must have at least one step")
            continue

        case_audit_at = case_audit_map.get(case_id, "")

        # Check step details and ordering
        prev_sort_key = None
        for step_idx, step in enumerate(steps):
            expected_step_no = step_idx + 1
            step_no = step.get("step_no")
            phase = step.get("phase")
            op = step.get("operation")
            state = step.get("state")
            sys_id = step.get("system_id", "")
            res_id = step.get("resource_id", "")
            ev_id = step.get("evidence_id", "")

            # Step number
            if step_no != expected_step_no:
                errors.append(f"Line {line_num}, step {step_idx}: expected step_no {expected_step_no}, got {step_no}")

            # Phase
            if phase not in PHASE_ORDER:
                errors.append(f"Line {line_num}, step {step_no}: invalid phase '{phase}'")
                continue

            # Status vs phase rules
            if deletion_status == "COMPLETE" and phase != "VERIFICATION":
                errors.append(f"Line {line_num}, step {step_no}: COMPLETE case cannot have phase '{phase}'")

            # Operation check
            if op not in OPERATION_ORDER.get(phase, {}):
                errors.append(f"Line {line_num}, step {step_no}: operation '{op}' not allowed in phase '{phase}'")
                continue

            # State check
            expected_state = ALLOWED_OP_STATE.get(op)
            if state != expected_state:
                errors.append(f"Line {line_num}, step {step_no}: operation '{op}' requires state '{expected_state}', got '{state}'")

            # Evidence ID constraints
            if phase == "FINDING":
                if not ev_id:
                    errors.append(f"Line {line_num}, step {step_no}: FINDING step must cite non-empty evidence_id")
            elif phase == "REMEDIATION":
                if ev_id != "":
                    errors.append(f"Line {line_num}, step {step_no}: REMEDIATION step must have empty evidence_id, got '{ev_id}'")
            elif phase == "VERIFICATION":
                if deletion_status == "COMPLETE" and not ev_id:
                    errors.append(f"Line {line_num}, step {step_no}: COMPLETE VERIFICATION step must cite evidence_id")
                elif deletion_status == "INCOMPLETE" and ev_id != "":
                    errors.append(f"Line {line_num}, step {step_no}: INCOMPLETE post-remediation VERIFICATION step must have empty evidence_id, got '{ev_id}'")

            # Temporal check: evidence captured_at must not be after audit_at
            if ev_id and ev_id in evidence_timestamps and case_audit_at:
                ev_time = evidence_timestamps[ev_id]
                if ev_time > case_audit_at:
                    errors.append(f"Line {line_num}, step {step_no}: evidence '{ev_id}' captured at {ev_time} > audit_at {case_audit_at}")

            # Ordering check
            p_val = PHASE_ORDER[phase]
            o_val = OPERATION_ORDER[phase][op]
            sort_key = (p_val, o_val, sys_id, res_id)
            if prev_sort_key is not None and prev_sort_key > sort_key:
                errors.append(f"Line {line_num}, step {step_no}: ordering violation. Key {sort_key} came after {prev_sort_key}")
            prev_sort_key = sort_key

    is_valid = len(errors) == 0
    if is_valid:
        print("SUCCESS: Output validation passed with 0 errors!")
    else:
        print(f"FAILURE: Output validation failed with {len(errors)} error(s):")
        for err in errors[:25]:
            print(f"  - {err}")
        if len(errors) > 25:
            print(f"  ... and {len(errors) - 25} more errors.")
    return is_valid, errors


def main():
    parser = argparse.ArgumentParser(description="Validate output.csv against schema and invariants")
    parser.add_argument("--file", default="output.csv", help="Path to output.csv to validate")
    parser.add_argument("--requests", default=os.path.join("dataset", "deletion_requests.csv"), help="Path to requests CSV")
    args = parser.parse_args()

    success, _ = validate_file(args.file, args.requests)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
