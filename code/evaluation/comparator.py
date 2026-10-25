"""
Independent comparator for HackerRank Orchestrate (October 2026) - Ghost Data Still Exists.

This comparator is completely independent of scorer.py.
It performs strict, non-lossy validation:
1. Rejects inner-join / zip() silent row drops.
2. Checks unique case IDs in candidate and exact case-ID set match against expected.
3. Compares deletion_status and parsed steps_json arrays semantically (ignoring key order and formatting whitespace).
4. Compares step fields strictly: step_no, phase, operation, system_id, resource_id, state, evidence_id.
5. Verifies array sequence order.
6. Flags missing cases, unexpected cases, duplicate cases, missing steps, extra steps, and field mismatches.
"""

from __future__ import annotations
import csv
import json
from typing import Dict, List, Any, Optional, Tuple


class ComparisonResult:
    def __init__(self):
        self.total_expected_cases: int = 0
        self.total_candidate_cases: int = 0
        self.missing_cases: List[str] = []
        self.unexpected_cases: List[str] = []
        self.duplicate_cases: List[str] = []
        self.status_mismatches: List[Tuple[str, str, str]] = []  # (case_id, cand_status, exp_status)
        self.step_sequence_mismatches: List[Dict[str, Any]] = []
        self.total_expected_steps: int = 0
        self.total_candidate_steps: int = 0
        self.matched_step_count: int = 0
        self.field_mismatches: Dict[str, int] = {
            "step_no": 0, "phase": 0, "operation": 0,
            "system_id": 0, "resource_id": 0, "state": 0, "evidence_id": 0
        }
        self.byte_exact_rows: int = 0

    @property
    def is_exact_match(self) -> bool:
        return (
            len(self.missing_cases) == 0 and
            len(self.unexpected_cases) == 0 and
            len(self.duplicate_cases) == 0 and
            len(self.status_mismatches) == 0 and
            len(self.step_sequence_mismatches) == 0 and
            self.total_candidate_steps == self.total_expected_steps and
            self.matched_step_count == self.total_expected_steps and
            sum(self.field_mismatches.values()) == 0
        )

    def summary(self) -> Dict[str, Any]:
        status_acc = 0.0
        seq_acc = 0.0
        if self.total_expected_cases > 0:
            status_acc = round((self.total_expected_cases - len(self.status_mismatches) - len(self.missing_cases)) / self.total_expected_cases * 100, 2)
            seq_acc = round((self.total_expected_cases - len(self.step_sequence_mismatches) - len(self.missing_cases)) / self.total_expected_cases * 100, 2)
        
        prec = round(self.matched_step_count / self.total_candidate_steps * 100, 2) if self.total_candidate_steps > 0 else 0.0
        rec = round(self.matched_step_count / self.total_expected_steps * 100, 2) if self.total_expected_steps > 0 else 0.0
        f1 = round(2 * prec * rec / (prec + rec), 2) if (prec + rec) > 0 else 0.0

        return {
            "exact_match": self.is_exact_match,
            "expected_cases": self.total_expected_cases,
            "candidate_cases": self.total_candidate_cases,
            "missing_cases_count": len(self.missing_cases),
            "unexpected_cases_count": len(self.unexpected_cases),
            "duplicate_cases_count": len(self.duplicate_cases),
            "status_accuracy_pct": status_acc,
            "sequence_accuracy_pct": seq_acc,
            "total_expected_steps": self.total_expected_steps,
            "total_candidate_steps": self.total_candidate_steps,
            "matched_steps": self.matched_step_count,
            "step_precision_pct": prec,
            "step_recall_pct": rec,
            "step_f1_pct": f1,
            "field_mismatches": self.field_mismatches,
            "byte_exact_rows": self.byte_exact_rows
        }


def load_csv_strictly(path: str) -> Tuple[List[str], Dict[str, dict], List[str]]:
    """
    Loads output CSV and returns (case_order, case_map, duplicates).
    Preserves exact file case ordering and detects duplicates without dropping.
    """
    case_order = []
    case_map = {}
    duplicates = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = row.get("case_id", "").strip()
            if not cid:
                continue
            if cid in case_map:
                duplicates.append(cid)
            case_map[cid] = row
            case_order.append(cid)
    return case_order, case_map, duplicates


def normalize_step(s: dict) -> dict:
    """Normalizes a single step dictionary to required fields."""
    return {
        "step_no": int(s.get("step_no", 0)),
        "phase": str(s.get("phase", "")).strip(),
        "system_id": str(s.get("system_id", "")).strip(),
        "resource_id": str(s.get("resource_id", "")).strip(),
        "operation": str(s.get("operation", "")).strip(),
        "state": str(s.get("state", "")).strip(),
        "evidence_id": str(s.get("evidence_id", "")).strip() if s.get("evidence_id") is not None else ""
    }


def compare_steps(cand_steps: List[dict], exp_steps: List[dict], ignore_step_no: bool = True) -> Tuple[int, Dict[str, list]]:
    """
    Compares candidate steps to expected steps using multiset matching.
    Each expected step is matched at most once without double-counting duplicates.
    Returns (matched_count, {'unmatched_candidate': [...], 'unmatched_expected': [...]}).
    """
    fields = ["phase", "operation", "system_id", "resource_id", "state", "evidence_id"]
    if not ignore_step_no:
        fields = ["step_no"] + fields

    matched = 0
    unmatched_exp = [normalize_step(e) for e in exp_steps]
    unmatched_cand = []

    for c in cand_steps:
        c_norm = normalize_step(c)
        found_idx = None
        for i, e_norm in enumerate(unmatched_exp):
            if all(c_norm.get(f) == e_norm.get(f) for f in fields):
                found_idx = i
                break
        if found_idx is not None:
            matched += 1
            unmatched_exp.pop(found_idx)
        else:
            unmatched_cand.append(c_norm)

    return matched, {"unmatched_candidate": unmatched_cand, "unmatched_expected": unmatched_exp}


def compare_outputs(candidate_path: str, expected_path: str) -> ComparisonResult:
    result = ComparisonResult()

    cand_order, cand_map, cand_dups = load_csv_strictly(candidate_path)
    exp_order, exp_map, exp_dups = load_csv_strictly(expected_path)

    result.total_candidate_cases = len(cand_order)
    result.total_expected_cases = len(exp_order)
    result.duplicate_cases = cand_dups

    cand_set = set(cand_map.keys())
    exp_set = set(exp_map.keys())

    result.missing_cases = sorted(list(exp_set - cand_set))
    result.unexpected_cases = sorted(list(cand_set - exp_set))

    # Evaluate all expected cases
    for cid in exp_order:
        exp_row = exp_map[cid]
        try:
            exp_steps = [normalize_step(s) for s in json.loads(exp_row.get("steps_json", "[]"))]
        except Exception:
            exp_steps = []
        result.total_expected_steps += len(exp_steps)

        if cid not in cand_map:
            continue

        cand_row = cand_map[cid]
        try:
            cand_steps = [normalize_step(s) for s in json.loads(cand_row.get("steps_json", "[]"))]
        except Exception:
            cand_steps = []
        result.total_candidate_steps += len(cand_steps)

        # Check raw byte / string equality
        if cand_row.get("steps_json", "").strip() == exp_row.get("steps_json", "").strip() and \
           cand_row.get("deletion_status", "").strip() == exp_row.get("deletion_status", "").strip():
            result.byte_exact_rows += 1

        # Check status
        cand_status = cand_row.get("deletion_status", "").strip()
        exp_status = exp_row.get("deletion_status", "").strip()
        if cand_status != exp_status:
            result.status_mismatches.append((cid, cand_status, exp_status))

        # Check step sequence equality
        step_seq_mismatch = False
        if len(cand_steps) != len(exp_steps):
            step_seq_mismatch = True
        else:
            for idx, (c_st, e_st) in enumerate(zip(cand_steps, exp_steps)):
                step_match = True
                for field in ["step_no", "phase", "operation", "system_id", "resource_id", "state", "evidence_id"]:
                    if c_st.get(field) != e_st.get(field):
                        result.field_mismatches[field] += 1
                        step_match = False
                if step_match:
                    result.matched_step_count += 1
                else:
                    step_seq_mismatch = True

        if step_seq_mismatch or cand_status != exp_status:
            result.step_sequence_mismatches.append({
                "case_id": cid,
                "cand_status": cand_status,
                "exp_status": exp_status,
                "cand_steps_count": len(cand_steps),
                "exp_steps_count": len(exp_steps),
                "cand_steps": cand_steps,
                "exp_steps": exp_steps
            })

    # Count extra steps from unexpected cases if any
    for cid in result.unexpected_cases:
        cand_row = cand_map[cid]
        try:
            cand_steps = json.loads(cand_row.get("steps_json", "[]"))
            result.total_candidate_steps += len(cand_steps)
        except Exception:
            pass

    return result
