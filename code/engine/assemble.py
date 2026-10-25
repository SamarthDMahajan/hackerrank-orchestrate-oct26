"""
Assembly module (L6) for HackerRank Orchestrate (October 2026)
Ghost Data Still Exists.

Enforces:
1. Strict Phase Ordering: FINDING -> REMEDIATION -> VERIFICATION
2. Operation Priority within Phase:
   - FINDING: REPORT_REMAINING_RECORD -> REPORT_EXPOSED_PII -> REPORT_ACTIVE_DATA_FLOW -> REPORT_RESTORE_RISK
   - REMEDIATION: DISABLE_DATA_FLOW -> BLOCK_RESTORE -> DELETE_RECORD -> REDACT_RECORD -> ANONYMIZE_RECORD
   - VERIFICATION: VERIFY_RECORD_ABSENT -> VERIFY_RECORD_PRESENT -> VERIFY_RECORD_REDACTED -> VERIFY_RECORD_ANONYMIZED -> VERIFY_DATA_FLOW_DISABLED -> VERIFY_RESTORE_BLOCKED
3. Secondary Sort Keys: system_id A->Z, resource_id A->Z
4. Consecutive step_no numbering from 1..N
5. Deterministic JSON serialization
"""

import json
from typing import List, Dict, Any

PHASE_ORDER = {
    "FINDING": 1,
    "REMEDIATION": 2,
    "VERIFICATION": 3,
}

OP_ORDER = {
    # Findings
    "REPORT_REMAINING_RECORD": 1,
    "REPORT_EXPOSED_PII": 2,
    "REPORT_ACTIVE_DATA_FLOW": 3,
    "REPORT_RESTORE_RISK": 4,
    # Remediation
    "DISABLE_DATA_FLOW": 1,
    "BLOCK_RESTORE": 2,
    "DELETE_RECORD": 3,
    "REDACT_RECORD": 4,
    "ANONYMIZE_RECORD": 5,
    # Verification
    "VERIFY_RECORD_ABSENT": 1,
    "VERIFY_RECORD_PRESENT": 2,
    "VERIFY_RECORD_REDACTED": 3,
    "VERIFY_RECORD_ANONYMIZED": 4,
    "VERIFY_DATA_FLOW_DISABLED": 5,
    "VERIFY_RESTORE_BLOCKED": 6,
}


def sort_key(step: Dict[str, Any]) -> tuple:
    p_rank = PHASE_ORDER.get(step["phase"], 99)
    op_rank = OP_ORDER.get(step["operation"], 99)
    sys_id = step["system_id"]
    res_id = step["resource_id"]
    return (p_rank, op_rank, sys_id, res_id)


def assemble_steps(raw_steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sorts steps by the proven invariant, deduplicates duplicate extractions,
    and assigns consecutive step_no (1..N).
    """
    sorted_steps = sorted(raw_steps, key=sort_key)
    deduped_steps = []
    seen = set()
    for s in sorted_steps:
        key = (s["phase"], s["system_id"], s["resource_id"], s["operation"], s["state"])
        if key in seen:
            continue
        seen.add(key)
        deduped_steps.append(s)

    numbered_steps = []
    for idx, s in enumerate(deduped_steps, start=1):
        numbered_steps.append({
            "step_no": idx,
            "phase": s["phase"],
            "system_id": s["system_id"],
            "resource_id": s["resource_id"],
            "operation": s["operation"],
            "state": s["state"],
            "evidence_id": s.get("evidence_id", "")
        })
    return numbered_steps


def serialize_steps(steps: List[Dict[str, Any]]) -> str:
    """
    Serializes steps list to deterministic JSON string.
    Uses compact separators (no spaces) matching ground truth format.
    """
    return json.dumps(steps, separators=(',', ':'))
