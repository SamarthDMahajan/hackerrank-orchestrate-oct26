"""
Data Discovery and Profiling Script for HackerRank Orchestrate (October 2026)
Ghost Data Still Exists

Performs read-only profiling of dataset/ and evidence files:
1. Profiles every CSV in dataset/
2. Deep profile of deletion_requests.csv
3. Enumeration and timestamp profiling of evidence files vs case audit_at
4. Testing email hash hypothesis (SHA-256 and other normalizations)
5. Reverse engineering ordering in dataset/sample_output.csv
"""

import os
import sys
import csv
import json
import re
import hashlib
from datetime import datetime
from collections import Counter, defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(REPO_ROOT, "dataset")
EVIDENCE_DIR = os.path.join(DATASET_DIR, "evidence")

def profile_csv(file_path):
    rel_path = os.path.relpath(file_path, REPO_ROOT)
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return {"file": rel_path, "total_rows": 0, "columns": []}
        
        rows = list(reader)
        total_rows = len(rows)
        col_profiles = []
        for i, col in enumerate(header):
            vals = [r[i] if i < len(r) else "" for r in rows]
            null_count = sum(1 for v in vals if v == "" or v is None)
            null_pct = (null_count / total_rows * 100.0) if total_rows > 0 else 0.0
            distinct_vals = set(vals)
            top_vals = Counter(vals).most_common(5)
            # Infer dtype
            dtype = "string"
            if total_rows > 0:
                non_null = [v for v in vals if v != ""]
                if non_null:
                    if all(re.match(r"^-?\d+$", v) for v in non_null):
                        dtype = "integer"
                    elif all(re.match(r"^-?\d+(\.\d+)?$", v) for v in non_null):
                        dtype = "float"
                    elif all(re.match(r"^\d{4}-\d{2}-\d{2}", v) for v in non_null):
                        dtype = "datetime_iso"
            
            col_profiles.append({
                "column": col,
                "dtype": dtype,
                "null_count": null_count,
                "null_pct": round(null_pct, 2),
                "distinct_count": len(distinct_vals),
                "top_5": [(k, v) for k, v in top_vals]
            })
        
        sample_rows = rows[:3] if total_rows >= 3 else rows
        return {
            "file": rel_path,
            "total_rows": total_rows,
            "header": header,
            "columns": col_profiles,
            "sample_rows": sample_rows
        }

def profile_deletion_requests():
    p = os.path.join(DATASET_DIR, "deletion_requests.csv")
    with open(p, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    statuses = Counter(r["reported_status"] for r in rows)
    req_dates = [r["requested_at"] for r in rows if r["requested_at"]]
    rep_dates = [r["reported_at"] for r in rows if r["reported_at"]]
    aud_dates = [r["audit_at"] for r in rows if r["audit_at"]]
    
    # Intent analysis based on request text keywords
    intent_keywords = {
        "deletion": ["delete", "remove", "erasure", "erase", "forget", "close my account", "purge", "wipe", "cancel account"],
        "access": ["access", "what data", "see what", "copy of", "view my data", "disclosure", "information about me"],
        "export": ["export", "download", "portability", "send me all", "file containing"],
        "correction": ["correct", "rectif", "update my", "change my name", "fix my", "wrong"],
        "marketing_opt_out": ["unsubscribe", "opt out", "stop sending", "marketing", "newsletter", "promotional"]
    }
    
    intent_counts = Counter()
    for r in rows:
        text = r["request_text"].lower()
        matched = []
        for intent, kws in intent_keywords.items():
            if any(kw in text for kw in kws):
                matched.append(intent)
        if not matched:
            intent_counts["unclassified"] += 1
        elif len(matched) == 1:
            intent_counts[matched[0]] += 1
        else:
            intent_counts["multiple:" + "+".join(matched)] += 1

    return {
        "total_cases": len(rows),
        "status_distribution": dict(statuses),
        "requested_at_range": (min(req_dates), max(req_dates)) if req_dates else None,
        "reported_at_range": (min(rep_dates), max(rep_dates)) if rep_dates else None,
        "audit_at_range": (min(aud_dates), max(aud_dates)) if aud_dates else None,
        "intent_distribution": dict(intent_counts)
    }

def test_hash_hypothesis():
    # 1. Test user_identities email to email_hash
    p_identities = os.path.join(DATASET_DIR, "user_identities.csv")
    with open(p_identities, "r", encoding="utf-8") as f:
        users = list(csv.DictReader(f))
    
    total_users = len(users)
    exact_sha256_lower_strip = 0
    exact_sha256_raw = 0
    exact_md5_lower_strip = 0
    exact_sha1_lower_strip = 0
    
    for u in users:
        email = u["email"]
        expected_hash = u["email_hash"]
        h_lower_strip = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
        h_raw = hashlib.sha256(email.encode("utf-8")).hexdigest()
        if h_lower_strip == expected_hash:
            exact_sha256_lower_strip += 1
        if h_raw == expected_hash:
            exact_sha256_raw += 1
        if hashlib.md5(email.strip().lower().encode("utf-8")).hexdigest() == expected_hash:
            exact_md5_lower_strip += 1
        if hashlib.sha1(email.strip().lower().encode("utf-8")).hexdigest() == expected_hash:
            exact_sha1_lower_strip += 1

    # Check evidence files for hash matches
    # Collect all known email hashes, user_ids, emails
    user_hashes = {u["email_hash"]: u["user_id"] for u in users if u["email_hash"]}
    user_emails = {u["email"].lower(): u["user_id"] for u in users if u["email"]}
    user_ids = {u["user_id"] for u in users}
    
    evidence_manifest = os.path.join(DATASET_DIR, "evidence_files.csv")
    with open(evidence_manifest, "r", encoding="utf-8") as f:
        ev_files = list(csv.DictReader(f))
    
    evidence_hash_hits = Counter()
    evidence_email_hits = Counter()
    evidence_user_id_hits = Counter()
    
    sha256_regex = re.compile(r"\b[a-f0-9]{64}\b", re.IGNORECASE)
    email_regex = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
    user_id_regex = re.compile(r"\buser_\d+\b")
    
    total_evidence_files_scanned = 0
    files_with_hashes = 0
    hash_occurrences_total = 0
    hash_occurrences_matching_user = 0
    
    for ev in ev_files:
        fpath = os.path.join(DATASET_DIR, ev["file_path"].replace("/", os.sep))
        if not os.path.exists(fpath):
            continue
        # Scan text-readable files
        if fpath.endswith((".log", ".json", ".sql", ".txt", ".csv")):
            total_evidence_files_scanned += 1
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                hashes_found = sha256_regex.findall(content)
                if hashes_found:
                    files_with_hashes += 1
                    for h in hashes_found:
                        hl = h.lower()
                        hash_occurrences_total += 1
                        if hl in user_hashes:
                            hash_occurrences_matching_user += 1
                            evidence_hash_hits[ev["file_id"]] += 1
                for em in email_regex.findall(content):
                    if em.lower() in user_emails:
                        evidence_email_hits[ev["file_id"]] += 1
                for uid in user_id_regex.findall(content):
                    if uid in user_ids:
                        evidence_user_id_hits[ev["file_id"]] += 1
            except Exception as e:
                pass
                
    return {
        "total_users": total_users,
        "exact_sha256_lower_strip_matches": exact_sha256_lower_strip,
        "exact_sha256_raw_matches": exact_sha256_raw,
        "match_pct_in_user_identities": round(exact_sha256_lower_strip / total_users * 100.0, 2),
        "total_text_evidence_scanned": total_evidence_files_scanned,
        "evidence_files_containing_sha256": files_with_hashes,
        "total_sha256_occurrences_in_evidence": hash_occurrences_total,
        "sha256_occurrences_matching_user_identities": hash_occurrences_matching_user,
        "evidence_files_with_user_hash_hits": len(evidence_hash_hits),
        "evidence_files_with_user_email_hits": len(evidence_email_hits),
        "evidence_files_with_user_id_hits": len(evidence_user_id_hits)
    }

def analyze_sample_output_ordering():
    p = os.path.join(DATASET_DIR, "sample_output.csv")
    with open(p, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        
    phase_order = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}
    finding_op_order = {
        "REPORT_REMAINING_RECORD": 0,
        "REPORT_EXPOSED_PII": 1,
        "REPORT_ACTIVE_DATA_FLOW": 2,
        "REPORT_RESTORE_RISK": 3
    }
    remediation_op_order = {
        "DISABLE_DATA_FLOW": 0,
        "BLOCK_RESTORE": 1,
        "DELETE_RECORD": 2,
        "REDACT_RECORD": 3,
        "ANONYMIZE_RECORD": 4
    }
    verification_op_order = {
        "VERIFY_RECORD_ABSENT": 0,
        "VERIFY_RECORD_PRESENT": 1,
        "VERIFY_RECORD_REDACTED": 2,
        "VERIFY_RECORD_ANONYMIZED": 3,
        "VERIFY_DATA_FLOW_DISABLED": 4,
        "VERIFY_RESTORE_BLOCKED": 5
    }
    
    def get_sort_key(step):
        p_val = phase_order.get(step["phase"], 99)
        if step["phase"] == "FINDING":
            o_val = finding_op_order.get(step["operation"], 99)
        elif step["phase"] == "REMEDIATION":
            o_val = remediation_op_order.get(step["operation"], 99)
        elif step["phase"] == "VERIFICATION":
            o_val = verification_op_order.get(step["operation"], 99)
        else:
            o_val = 99
        return (p_val, o_val, step.get("system_id", ""), step.get("resource_id", ""))

    violations = []
    total_steps_checked = 0
    statuses = Counter()
    
    for r in rows:
        cid = r["case_id"]
        status = r["deletion_status"]
        statuses[status] += 1
        steps = json.loads(r["steps_json"])
        
        # Check consecutive step_no starting from 1
        for idx, s in enumerate(steps):
            total_steps_checked += 1
            expected_step_no = idx + 1
            if s.get("step_no") != expected_step_no:
                violations.append({
                    "case_id": cid,
                    "issue": f"step_no mismatch: expected {expected_step_no}, got {s.get('step_no')}",
                    "step": s
                })
        
        # Check pairwise ordering
        for i in range(len(steps) - 1):
            s1 = steps[i]
            s2 = steps[i+1]
            k1 = get_sort_key(s1)
            k2 = get_sort_key(s2)
            if k1 > k2:
                violations.append({
                    "case_id": cid,
                    "issue": f"Order violation at index {i} -> {i+1}",
                    "step_before": s1,
                    "step_after": s2,
                    "key_before": k1,
                    "key_after": k2
                })
                
    return {
        "total_sample_cases": len(rows),
        "status_distribution": dict(statuses),
        "total_steps_checked": total_steps_checked,
        "violations_count": len(violations),
        "violations": violations
    }

def analyze_evidence_timestamps_vs_cases():
    # Load deletion_requests
    p_req = os.path.join(DATASET_DIR, "deletion_requests.csv")
    with open(p_req, "r", encoding="utf-8") as f:
        cases = list(csv.DictReader(f))
        
    p_ev = os.path.join(DATASET_DIR, "evidence_files.csv")
    with open(p_ev, "r", encoding="utf-8") as f:
        evidence = list(csv.DictReader(f))
        
    # Analyze evidence formats
    formats = Counter(os.path.splitext(e["file_path"])[1].lower() for e in evidence)
    origins = Counter(e["origin"] for e in evidence)
    
    ev_dates = [e["captured_at"] for e in evidence if e["captured_at"]]
    min_ev_date = min(ev_dates) if ev_dates else None
    max_ev_date = max(ev_dates) if ev_dates else None
    
    # Count per case how many evidence files are captured after audit_at
    cases_with_future_evidence = 0
    future_ev_counts_per_case = []
    
    for c in cases:
        audit_at = c["audit_at"]
        after_count = sum(1 for e in evidence if e["captured_at"] > audit_at)
        if after_count > 0:
            cases_with_future_evidence += 1
            future_ev_counts_per_case.append(after_count)
            
    return {
        "total_evidence_files": len(evidence),
        "formats_distribution": dict(formats),
        "origins_distribution": dict(origins),
        "captured_at_range": (min_ev_date, max_ev_date),
        "cases_with_evidence_after_audit_at": cases_with_future_evidence,
        "total_cases": len(cases),
        "min_future_evidence_per_case": min(future_ev_counts_per_case) if future_ev_counts_per_case else 0,
        "max_future_evidence_per_case": max(future_ev_counts_per_case) if future_ev_counts_per_case else 0,
        "avg_future_evidence_per_case": round(sum(future_ev_counts_per_case) / len(future_ev_counts_per_case), 2) if future_ev_counts_per_case else 0
    }

def run_all():
    print("Profiling dataset files...")
    csv_files = [
        "deletion_requests.csv",
        "sample_deletion_requests.csv",
        "sample_output.csv",
        "user_identities.csv",
        "user_audit_log.csv",
        "system_activity.csv",
        "deletion_rules.csv",
        "evidence_files.csv",
        "output.csv"
    ]
    profiles = {}
    for cf in csv_files:
        p = os.path.join(DATASET_DIR, cf)
        profiles[cf] = profile_csv(p)
        
    print("Profiling deletion requests...")
    req_profile = profile_deletion_requests()
    
    print("Testing hash hypothesis...")
    hash_results = test_hash_hypothesis()
    
    print("Analyzing sample output ordering...")
    order_results = analyze_sample_output_ordering()
    
    print("Analyzing evidence timestamps vs cases...")
    ev_time_results = analyze_evidence_timestamps_vs_cases()
    
    out = {
        "csv_profiles": profiles,
        "deletion_requests_profile": req_profile,
        "hash_hypothesis": hash_results,
        "sample_output_ordering": order_results,
        "evidence_timing": ev_time_results
    }
    
    out_path = os.path.join(REPO_ROOT, "docs", "discovery_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"Discovery raw data saved to {out_path}")

if __name__ == "__main__":
    run_all()
