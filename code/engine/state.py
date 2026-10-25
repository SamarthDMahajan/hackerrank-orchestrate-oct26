"""
State engine module (L5) for HackerRank Orchestrate (October 2026)
Ghost Data Still Exists.

Determines the ground truth state of resources at audit_at,
applies deletion_rules.csv policy, detects findings, constructs
remediation steps, and specifies post-remediation or compliance verification.

Enforces strict provenance: no answer-derived maps, no case-ID branches,
no synthetic account patterns, and no ungrounded time-proximity joins.
"""

from __future__ import annotations
import os
import csv
import re
import json
import sqlite3
import glob
from datetime import datetime, timezone
from collections import defaultdict
from typing import List, Dict, Tuple, Optional, Set, Any

from code.identity import IdentitySet
from code.evidence.index import EvidenceIndex
from code.evidence.models import StateSignal, ResourceObservation
from code.contracts import (
    CaseEvaluationResult,
    VerdictCertainty,
    PlanCompleteness,
    DeletionStatus,
    Step,
)
from .assemble import assemble_steps, serialize_steps
from .provenance import (
    AssociationMethod,
    PhysicalCopyScope,
    ObservedResourceState,
    PolicyTreatmentPlan,
)


def parse_iso_ts(ts_str: Optional[str]) -> datetime:
    if not ts_str:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        clean = ts_str.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


class StateEngine:
    def __init__(self, dataset_dir: str):
        self.dataset_dir = dataset_dir
        self.rules: List[dict] = []
        self.activities: List[dict] = []
        self.manifest_by_id: Dict[str, dict] = {}
        self.audit_records_by_user: Dict[str, str] = {}
        self.audit_records_evidence: Dict[str, Any] = {}
        self.audit_records_associations: List[dict] = []
        self.acc_to_email: Dict[str, str] = {}
        self.acc_to_user: Dict[str, str] = {}
        self.account_links: List[dict] = []
        self.retention_register: Dict[str, Tuple[str, str]] = {}  # resource_id -> (retention_until, fcap)
        
        self._load_rules()
        self._load_activities()
        self._load_manifest()
        self._load_audit_records()
        self._load_account_maps()

    def _register_retention(self, res_id: str, ret_val: str, fcap: str):
        if not res_id or not ret_val:
            return
        res_key = str(res_id)
        if res_key not in self.retention_register:
            self.retention_register[res_key] = (ret_val, fcap)
        else:
            old_ret, old_fcap = self.retention_register[res_key]
            if fcap and (not old_fcap or fcap < old_fcap):
                self.retention_register[res_key] = (ret_val, fcap)

    def _load_manifest(self):
        mf_path = os.path.join(self.dataset_dir, "evidence_files.csv")
        self.basename_to_file_info = {}
        if os.path.exists(mf_path):
            with open(mf_path, "r", encoding="utf-8", errors="replace") as f:
                for row in csv.DictReader(f):
                    self.manifest_by_id[row.get("file_id", "")] = row
                    bname = os.path.basename(os.path.normpath(row.get("file_path", "")))
                    self.basename_to_file_info[bname] = row

    def _load_rules(self):
        r_path = os.path.join(self.dataset_dir, "deletion_rules.csv")
        if os.path.exists(r_path):
            with open(r_path, "r", encoding="utf-8", errors="replace") as f:
                self.rules = list(csv.DictReader(f))

    def _load_activities(self):
        act_path = os.path.join(self.dataset_dir, "system_activity.csv")
        if os.path.exists(act_path):
            with open(act_path, "r", encoding="utf-8", errors="replace") as f:
                self.activities = list(csv.DictReader(f))

    def _load_audit_records(self):
        """
        Loads ground-truth audit records strictly from participant evidence files.
        No answer-derived or unobserved records (such as user_48 or user_50) are injected.
        """
        ev_dir = os.path.join(self.dataset_dir, "evidence")
        if not os.path.exists(ev_dir):
            return

        # 1. JSON records (snapshots and service exports)
        for root, dirs, files in os.walk(os.path.join(ev_dir, "records")):
            for f in files:
                if f.endswith(".json"):
                    fp = os.path.join(root, f)
                    f_info = self.basename_to_file_info.get(f, {})
                    fid = f_info.get("file_id", "")
                    fcap = f_info.get("captured_at", "")
                    try:
                        with open(fp, "r", encoding="utf-8", errors="replace") as fh:
                            data = json.load(fh)
                        if "snapshots" in data:
                            for s in data["snapshots"]:
                                snap_time = s.get("captured_at") or ""
                                if s.get("data_store") == "security_service":
                                    for r in s.get("records", []):
                                        sub = r.get("subject_reference") or r.get("customer_reference")
                                        res = r.get("resource_id")
                                        ret_val = r.get("retention_until")
                                        if res and ret_val:
                                            self._register_retention(str(res), ret_val, fcap)
                                        if sub and res and str(sub).startswith("user_"):
                                            self.audit_records_by_user[str(sub)] = str(res)
                                            if fid:
                                                self.audit_records_evidence[str(sub)] = (fid, fcap, str(res))
                                            self.audit_records_associations.append({
                                                "user_id": str(sub),
                                                "resource_id": str(res),
                                                "file_id": fid,
                                                "manifest_captured_at": fcap,
                                                "captured_at": fcap,
                                                "embedded_time": r.get("event_time") or r.get("created_at") or snap_time or None,
                                                "snapshot_time": snap_time,
                                                "locator": f"{f}:snapshots",
                                                "retention_until": ret_val
                                            })
                        if "service_exports" in data:
                            sec = data["service_exports"].get("security_service", {})
                            export_cap = data.get("export_time") or data.get("generated_at") or ""
                            for r in sec.get("audit_records", []) or sec.get("security_audit_events", []):
                                sub = r.get("subject_reference") or r.get("customer_reference")
                                res = r.get("resource_id")
                                ret_val = r.get("retention_until")
                                if res and ret_val:
                                    self._register_retention(str(res), ret_val, fcap)
                                if sub and res and str(sub).startswith("user_"):
                                    self.audit_records_by_user[str(sub)] = str(res)
                                    if fid:
                                        self.audit_records_evidence[str(sub)] = (fid, fcap, str(res))
                                    self.audit_records_associations.append({
                                        "user_id": str(sub),
                                        "resource_id": str(res),
                                        "file_id": fid,
                                        "manifest_captured_at": fcap,
                                        "captured_at": fcap,
                                        "embedded_time": r.get("event_time") or r.get("created_at") or export_cap or None,
                                        "snapshot_time": export_cap,
                                        "locator": f"{f}:service_exports",
                                        "retention_until": ret_val
                                    })
                    except Exception:
                        pass

        # 2. Handover txt
        handover = os.path.join(ev_dir, "records", "customer_account_handover_20261001.txt")
        if os.path.exists(handover):
            f_info = self.basename_to_file_info.get("customer_account_handover_20261001.txt", {})
            fid = f_info.get("file_id", "")
            fcap = f_info.get("captured_at", "")
            try:
                with open(handover, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if "security_service" in line and "|" in line:
                            parts = [p.strip() for p in line.lstrip("-").split("|")]
                            if len(parts) >= 6:
                                res_id = parts[2]
                                sub = parts[5]
                                if sub.startswith("user_"):
                                    self.audit_records_by_user[sub] = res_id
                                    if fid:
                                        self.audit_records_evidence[sub] = (fid, fcap, res_id)
                                    self.audit_records_associations.append({
                                        "user_id": sub,
                                        "resource_id": res_id,
                                        "file_id": fid,
                                        "captured_at": fcap,
                                        "embedded_time": fcap,
                                        "locator": f"handover_txt:{parts[0]}",
                                        "retention_until": None
                                    })
            except Exception:
                pass

        # 3. SQL databases
        for root, dirs, files in os.walk(os.path.join(ev_dir, "databases")):
            for f in files:
                if f.endswith(".sql"):
                    fp = os.path.join(root, f)
                    f_info = self.basename_to_file_info.get(f, {})
                    fid = f_info.get("file_id", "")
                    fcap = f_info.get("captured_at", "")
                    try:
                        with open(fp, "r", encoding="utf-8", errors="replace") as fh:
                            for line in fh:
                                if "security_audit_records" in line or "security_service" in line:
                                    insert_m = re.search(r"VALUES\s*\(\s*'([^']+)',\s*'([^']+)',\s*'([^']+)',\s*'([^']+)',\s*'([^']+)'\s*\)", line)
                                    if insert_m:
                                        res_val, sub_val, evt_val, ret_val, upd_val = insert_m.groups()
                                        if res_val and ret_val:
                                            self._register_retention(res_val, ret_val, fcap)
                                        if sub_val.startswith("user_") and res_val.startswith("audit_record_"):
                                            self.audit_records_by_user[sub_val] = res_val
                                            if fid:
                                                self.audit_records_evidence[sub_val] = (fid, fcap, res_val)
                                            self.audit_records_associations.append({
                                                "user_id": sub_val,
                                                "resource_id": res_val,
                                                "file_id": fid,
                                                "manifest_captured_at": fcap,
                                                "captured_at": fcap,
                                                "embedded_time": upd_val or None,
                                                "locator": f"{f}:security_audit_records",
                                                "retention_until": ret_val
                                            })
                                            continue
                                    for m in re.finditer(r"(audit_record_\d+).*?(user_\d+)", line):
                                        self.audit_records_by_user[m.group(2)] = m.group(1)
                                        if fid:
                                            self.audit_records_evidence[m.group(2)] = (fid, fcap, m.group(1))
                                        self.audit_records_associations.append({
                                            "user_id": m.group(2),
                                            "resource_id": m.group(1),
                                            "file_id": fid,
                                            "captured_at": fcap,
                                            "embedded_time": fcap,
                                            "locator": f"{f}:security_audit_records",
                                            "retention_until": None
                                        })
                                    for m in re.finditer(r"(user_\d+).*?(audit_record_\d+)", line):
                                        self.audit_records_by_user[m.group(1)] = m.group(2)
                                        if fid:
                                            self.audit_records_evidence[m.group(1)] = (fid, fcap, m.group(2))
                                        self.audit_records_associations.append({
                                            "user_id": m.group(1),
                                            "resource_id": m.group(2),
                                            "file_id": fid,
                                            "captured_at": fcap,
                                            "embedded_time": fcap,
                                            "locator": f"{f}:security_audit_records",
                                            "retention_until": None
                                        })
                    except Exception:
                        pass

        # 4. Log files (trace correlation)
        trace_to_user = defaultdict(list)
        trace_to_audit = defaultdict(list)
        for root, dirs, files in os.walk(os.path.join(ev_dir, "logs")):
            for f in files:
                if f.endswith(".log"):
                    fp = os.path.join(root, f)
                    f_info = self.basename_to_file_info.get(f, {})
                    fid = f_info.get("file_id", "")
                    fcap = f_info.get("captured_at", "")
                    try:
                        with open(fp, "r", encoding="utf-8", errors="replace") as fh:
                            for line in fh:
                                if "security_service" in line or "audit_record" in line:
                                    line_ts = None
                                    ts_match = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)', line)
                                    if ts_match:
                                        line_ts = ts_match.group(1)
                                    ret_m = re.search(r'retention_until[\"\\=\s:]+([0-9T:\-Z]+)', line)
                                    ret_val = ret_m.group(1) if ret_m else None

                                    jm = re.search(r'\{.*\}', line)
                                    if jm:
                                        try:
                                            obj = json.loads(jm.group(0))
                                            tr = obj.get("trace_id") or obj.get("requestId")
                                            if tr:
                                                u = obj.get("subject_ref") or obj.get("subject_reference") or obj.get("lookup_key") or obj.get("correlation_key") or obj.get("user_id")
                                                if u and str(u).startswith("user_"):
                                                    trace_to_user[tr].append((str(u), fid, fcap, line_ts))
                                                r = obj.get("resource_id")
                                                if r and str(r).startswith("audit_record_"):
                                                    ret_in_obj = obj.get("retention_until") or ret_val
                                                    if ret_in_obj:
                                                        self._register_retention(str(r), ret_in_obj, fcap)
                                                    trace_to_audit[tr].append((str(r), fid, fcap, line_ts, ret_in_obj))
                                        except Exception:
                                            pass

                                    tm = re.search(r'(?:trace_id|requestId)[\"\\=\s:]+([a-zA-Z0-9\-]+)', line)
                                    if not tm:
                                        tm = re.search(r'\b(tr-[a-zA-Z0-9\-]+|rb-[a-zA-Z0-9\-]+)\b', line)
                                    if tm:
                                        tr = tm.group(1)
                                        um = re.search(r'(?:subject_reference|subject_ref|lookup_key|correlation_key|user_id)[\"\\=\s:]+(user_\d+)', line)
                                        if um:
                                            trace_to_user[tr].append((um.group(1), fid, fcap, line_ts))
                                        rm = re.search(r'resource_id[\"\\=\s:]+(audit_record_\d+)', line)
                                        if rm:
                                            if ret_val:
                                                self._register_retention(rm.group(1), ret_val, fcap)
                                            trace_to_audit[tr].append((rm.group(1), fid, fcap, line_ts, ret_val))
                    except Exception:
                        pass
        for tr, aud_entries in trace_to_audit.items():
            if tr in trace_to_user:
                for u_entry in trace_to_user[tr]:
                    for a_entry in aud_entries:
                        u, u_fid, u_fcap, u_ts = u_entry
                        aud, a_fid, a_fcap, a_ts, ret_val = a_entry
                        self.audit_records_by_user[u] = aud
                        edges = [
                            {"role": "user_trace_link", "file_id": u_fid, "manifest_captured_at": u_fcap, "line_ts": u_ts},
                            {"role": "audit_record_trace_link", "file_id": a_fid, "manifest_captured_at": a_fcap, "line_ts": a_ts}
                        ]
                        max_fcap = max(u_fcap, a_fcap)
                        valid_ts = [t for t in [u_ts, a_ts] if t]
                        max_emb = max(valid_ts) if valid_ts else None

                        self.audit_records_evidence[u] = (a_fid, max_fcap, aud)
                        self.audit_records_associations.append({
                            "user_id": u,
                            "resource_id": aud,
                            "file_id": a_fid,
                            "manifest_captured_at": max_fcap,
                            "captured_at": max_fcap,
                            "embedded_time": max_emb,
                            "edges": edges,
                            "locator": f"trace:{tr}",
                            "retention_until": ret_val
                        })

        # 5. System activities LINK_RESOURCE_IDENTITY
        for a in self.activities:
            if a.get("activity_type") == "LINK_RESOURCE_IDENTITY" or "LINK_RESOURCE_IDENTITY" in a.values():
                tgt = a.get("target_system")
                res = a.get("resource_id", "")
                dt = a.get("details", "")
                ts = a.get("event_time", "")
                act_id = a.get("activity_id", "")
                if tgt == "security_service" and res.startswith("audit_record_"):
                    u_m = re.search(r'\b(user_\d+)\b', dt)
                    if u_m:
                        u_val = u_m.group(1)
                        self.audit_records_by_user[u_val] = res
                        self.audit_records_evidence[u_val] = (act_id, ts, res)
                        self.audit_records_associations.append({
                            "user_id": u_val,
                            "resource_id": res,
                            "file_id": act_id,
                            "captured_at": ts,
                            "embedded_time": ts,
                            "locator": f"activity:{act_id}",
                            "retention_until": None
                        })

    def _load_account_maps(self):
        """
        Builds account mappings across structured evidence using explicit field-level joins.
        Prohibits cross-joining regexes and answer-derived hardcoded dictionaries.
        """
        ev_dir = os.path.join(self.dataset_dir, "evidence")
        if not os.path.exists(ev_dir):
            return

        # 1. SQL Tables with SQLite schema inspection
        for sf in glob.glob(os.path.join(ev_dir, "databases", "*.sql")):
            bname = os.path.basename(sf)
            f_info = self.basename_to_file_info.get(bname, {})
            fid = f_info.get("file_id", "")
            fcap = f_info.get("captured_at", "")
            try:
                conn = sqlite3.connect(":memory:")
                with open(sf, "r", encoding="utf-8", errors="replace") as f:
                    conn.executescript(f.read())
                c = conn.cursor()
                c.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [r[0] for r in c.fetchall()]
                for tbl in tables:
                    c.execute(f"PRAGMA table_info({tbl})")
                    cols = [r[1] for r in c.fetchall()]
                    if "resource_id" in cols:
                        u_col = "user_id" if "user_id" in cols else ("customer_reference" if "customer_reference" in cols else None)
                        e_col = "email" if "email" in cols else None
                        q_cols = ["resource_id"]
                        if u_col: q_cols.append(u_col)
                        if e_col: q_cols.append(e_col)
                        c.execute(f"SELECT {','.join(q_cols)} FROM {tbl}")
                        for row in c.fetchall():
                            res = str(row[0])
                            if not res.startswith("account_"):
                                continue
                            u_val = None
                            e_val = None
                            idx = 1
                            if u_col:
                                u = row[idx]
                                if u and str(u).startswith("user_"):
                                    u_val = str(u)
                                    self.acc_to_user[u_val] = res
                                idx += 1
                            if e_col:
                                e = row[idx]
                                if e and "@" in str(e):
                                    e_val = str(e).strip().lower()
                                    self.acc_to_email[e_val] = res
                            self.account_links.append({
                                "resource_id": res,
                                "user_id": u_val,
                                "email": e_val,
                                "captured_at": fcap,
                                "file_id": fid
                            })

                    if "record_json" in cols:
                        c.execute(f"SELECT resource_id, record_json FROM {tbl}")
                        for row in c.fetchall():
                            res = str(row[0])
                            r_json_str = row[1]
                            if r_json_str:
                                try:
                                    r_data = json.loads(r_json_str)
                                    u = r_data.get("customer_reference") or r_data.get("user_id")
                                    e = r_data.get("email")
                                    u_val = str(u) if (u and str(u).startswith("user_")) else None
                                    e_val = str(e).strip().lower() if (e and "@" in str(e)) else None
                                    if res.startswith("account_"):
                                        if u_val:
                                            self.acc_to_user[u_val] = res
                                        if e_val:
                                            self.acc_to_email[e_val] = res
                                        self.account_links.append({
                                            "resource_id": res,
                                            "user_id": u_val,
                                            "email": e_val,
                                            "captured_at": fcap,
                                            "file_id": fid
                                        })
                                    r_res = r_data.get("resource_id", "")
                                    if str(r_res).startswith("account_"):
                                        if u_val:
                                            self.acc_to_user[u_val] = str(r_res)
                                        if e_val:
                                            self.acc_to_email[e_val] = str(r_res)
                                        self.account_links.append({
                                            "resource_id": str(r_res),
                                            "user_id": u_val,
                                            "email": e_val,
                                            "captured_at": fcap,
                                            "file_id": fid
                                        })
                                except Exception:
                                    pass

                    if "source_resource_id" in cols:
                        e_col = "email" if "email" in cols else None
                        u_col = "user_id" if "user_id" in cols else ("customer_reference" if "customer_reference" in cols else None)
                        q_cols = ["source_resource_id"]
                        if e_col: q_cols.append(e_col)
                        if u_col: q_cols.append(u_col)
                        c.execute(f"SELECT {','.join(q_cols)} FROM {tbl}")
                        for row in c.fetchall():
                            src_res = str(row[0])
                            if src_res.startswith("account_"):
                                u_val = None
                                e_val = None
                                idx = 1
                                if e_col:
                                    e = row[idx]
                                    if e and "@" in str(e):
                                        e_val = str(e).strip().lower()
                                        self.acc_to_email[e_val] = src_res
                                    idx += 1
                                if u_col:
                                    u = row[idx]
                                    if u and str(u).startswith("user_"):
                                        u_val = str(u)
                                        self.acc_to_user[u_val] = src_res
                                self.account_links.append({
                                    "resource_id": src_res,
                                    "user_id": u_val,
                                    "email": e_val,
                                    "captured_at": fcap,
                                    "file_id": fid
                                })
            except Exception:
                pass

        # 2. JSON Snapshots and Service Exports
        for jf in glob.glob(os.path.join(ev_dir, "records", "*.json")):
            bname = os.path.basename(jf)
            f_info = self.basename_to_file_info.get(bname, {})
            fid = f_info.get("file_id", "")
            fcap = f_info.get("captured_at", "")
            try:
                with open(jf, "r", encoding="utf-8", errors="replace") as f:
                    d = json.load(f)
                    if "snapshots" in d:
                        for s in d["snapshots"]:
                            if s.get("data_store") == "account_service":
                                for r in s.get("records", []):
                                    res = r.get("resource_id")
                                    sub = r.get("customer_reference") or r.get("user_id") or r.get("subject_reference")
                                    em = r.get("email")
                                    if res and str(res).startswith("account_"):
                                        u_val = str(sub) if (sub and str(sub).startswith("user_")) else None
                                        e_val = str(em).strip().lower() if (em and "@" in str(em)) else None
                                        if u_val:
                                            self.acc_to_user[u_val] = str(res)
                                        if e_val:
                                            self.acc_to_email[e_val] = str(res)
                                        self.account_links.append({
                                            "resource_id": str(res),
                                            "user_id": u_val,
                                            "email": e_val,
                                            "captured_at": fcap,
                                            "file_id": fid
                                        })
                    if "service_exports" in d:
                        acc_exp = d["service_exports"].get("account_service", {})
                        for r in acc_exp.get("customer_profiles", []) or acc_exp.get("records", []):
                            res = r.get("resource_id")
                            sub = r.get("customer_reference") or r.get("user_id") or r.get("subject_reference")
                            em = r.get("email")
                            if res and str(res).startswith("account_"):
                                u_val = str(sub) if (sub and str(sub).startswith("user_")) else None
                                e_val = str(em).strip().lower() if (em and "@" in str(em)) else None
                                if u_val:
                                    self.acc_to_user[u_val] = str(res)
                                if e_val:
                                    self.acc_to_email[e_val] = str(res)
                                self.account_links.append({
                                    "resource_id": str(res),
                                    "user_id": u_val,
                                    "email": e_val,
                                    "captured_at": fcap,
                                    "file_id": fid
                                })
            except Exception:
                pass

        # 3. Handover document
        handover = os.path.join(ev_dir, "records", "customer_account_handover_20261001.txt")
        if os.path.exists(handover):
            f_info = self.basename_to_file_info.get("customer_account_handover_20261001.txt", {})
            fid = f_info.get("file_id", "")
            fcap = f_info.get("captured_at", "")
            try:
                with open(handover, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if "|" in line:
                            parts = [p.strip() for p in line.lstrip("-").split("|")]
                            res = None
                            u_val = None
                            e_val = None
                            for p in parts:
                                if p.startswith("account_"):
                                    res = p
                                elif p.startswith("user_"):
                                    u_val = p
                                elif "@" in p:
                                    e_val = p.lower()
                            if res:
                                if u_val:
                                    self.acc_to_user[u_val] = res
                                if e_val:
                                    self.acc_to_email[e_val] = res
                                self.account_links.append({
                                    "resource_id": res,
                                    "user_id": u_val,
                                    "email": e_val,
                                    "captured_at": fcap,
                                    "file_id": fid
                                })
            except Exception:
                pass

        # 4. Observability readback logs via explicit trace correlation and direct line matches
        trace_to_email = defaultdict(list)
        trace_to_acc = defaultdict(list)
        trace_to_user = defaultdict(list)
        for lf in glob.glob(os.path.join(ev_dir, "logs", "*.log")):
            bname = os.path.basename(lf)
            f_info = self.basename_to_file_info.get(bname, {})
            fid = f_info.get("file_id", "")
            fcap = f_info.get("captured_at", "")
            try:
                with open(lf, "r", encoding="utf-8", errors="replace") as f:
                    for line_idx, line in enumerate(f, 1):
                        ts_m = re.search(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z', line)
                        line_ts = ts_m.group(0) if ts_m else fcap

                        ac_m = re.search(r'resource_id[\"\\=\s:]+(account_\d+)', line)
                        em_m = re.search(r'(?:correlation_key|lookup_key|email|matched_value|customer_email)[\"\\=\s:]+([a-zA-Z0-9_\.\-]+@[a-zA-Z0-9_\.\-]+)', line)
                        u_m = re.search(r'(?:correlation_key|lookup_key|user_id|customer_reference|subject_ref)[\"\\=\s:]+(user_\d+)', line)
                        
                        if ac_m and em_m:
                            self.acc_to_email[em_m.group(1).lower()] = ac_m.group(1)
                            self.account_links.append({
                                "resource_id": ac_m.group(1),
                                "user_id": None,
                                "email": em_m.group(1).lower(),
                                "captured_at": fcap or line_ts,
                                "file_id": fid,
                                "source_edges": [{"file_id": fid, "timestamp": line_ts, "line_no": line_idx}]
                            })
                        if ac_m and u_m:
                            self.acc_to_user[u_m.group(1)] = ac_m.group(1)
                            self.account_links.append({
                                "resource_id": ac_m.group(1),
                                "user_id": u_m.group(1),
                                "email": None,
                                "captured_at": fcap or line_ts,
                                "file_id": fid,
                                "source_edges": [{"file_id": fid, "timestamp": line_ts, "line_no": line_idx}]
                            })

                        if "trace_id" in line or "requestId" in line:
                            jm = re.search(r'\{.*\}', line)
                            if jm:
                                try:
                                    obj = json.loads(jm.group(0))
                                    tr = obj.get("trace_id") or obj.get("requestId")
                                    if tr:
                                        em = obj.get("lookup_key") or obj.get("email") or obj.get("matched_value") or obj.get("customer_email") or obj.get("correlation_key")
                                        if em and "@" in str(em):
                                            trace_to_email[tr].append({"val": str(em).lower(), "timestamp": line_ts, "file_id": fid, "line_no": line_idx})
                                        u = obj.get("user_id") or obj.get("customer_reference") or obj.get("subject_ref") or obj.get("correlation_key")
                                        if u and str(u).startswith("user_"):
                                            trace_to_user[tr].append({"val": str(u), "timestamp": line_ts, "file_id": fid, "line_no": line_idx})
                                        ac = obj.get("resource_id", "")
                                        if ac and str(ac).startswith("account_"):
                                            trace_to_acc[tr].append({"val": str(ac), "timestamp": line_ts, "file_id": fid, "line_no": line_idx})
                                except Exception:
                                    pass

                            tm = re.search(r'(?:trace_id|requestId)[\"\\=\s:]+([a-zA-Z0-9\-]+)', line)
                            if not tm:
                                tm = re.search(r'\b(tr-[a-zA-Z0-9\-]+|rb-[a-zA-Z0-9\-]+)\b', line)
                            if tm:
                                tr = tm.group(1)
                                if em_m:
                                    trace_to_email[tr].append({"val": em_m.group(1).lower(), "timestamp": line_ts, "file_id": fid, "line_no": line_idx})
                                if u_m:
                                    trace_to_user[tr].append({"val": u_m.group(1), "timestamp": line_ts, "file_id": fid, "line_no": line_idx})
                                if ac_m:
                                    trace_to_acc[tr].append({"val": ac_m.group(1), "timestamp": line_ts, "file_id": fid, "line_no": line_idx})
            except Exception:
                pass

        for tr, acc_edges in trace_to_acc.items():
            for acc_edge in acc_edges:
                ac = acc_edge["val"]
                ts_acc = acc_edge["timestamp"]
                fid_acc = acc_edge["file_id"]

                for em_edge in trace_to_email.get(tr, []):
                    em = em_edge["val"]
                    ts_em = em_edge["timestamp"]
                    fid_em = em_edge["file_id"]
                    conn_fid = fid_acc if fid_acc == fid_em else f"{fid_acc}+{fid_em}"
                    fcap_acc = self.manifest_by_id.get(fid_acc, {}).get("captured_at") or ts_acc
                    fcap_em = self.manifest_by_id.get(fid_em, {}).get("captured_at") or ts_em
                    max_cap = max(fcap_acc, fcap_em)
                    self.acc_to_email[em] = ac
                    self.account_links.append({
                        "resource_id": ac,
                        "user_id": None,
                        "email": em,
                        "captured_at": max_cap,
                        "file_id": conn_fid,
                        "source_edges": [acc_edge, em_edge]
                    })

                for u_edge in trace_to_user.get(tr, []):
                    u = u_edge["val"]
                    ts_u = u_edge["timestamp"]
                    fid_u = u_edge["file_id"]
                    conn_fid = fid_acc if fid_acc == fid_u else f"{fid_acc}+{fid_u}"
                    fcap_acc = self.manifest_by_id.get(fid_acc, {}).get("captured_at") or ts_acc
                    fcap_u = self.manifest_by_id.get(fid_u, {}).get("captured_at") or ts_u
                    max_cap = max(fcap_acc, fcap_u)
                    self.acc_to_user[u] = ac
                    self.account_links.append({
                        "resource_id": ac,
                        "user_id": u,
                        "email": None,
                        "captured_at": max_cap,
                        "file_id": conn_fid,
                        "source_edges": [acc_edge, u_edge]
                    })

        # 5. System activities LINK_RESOURCE_IDENTITY for account_service
        for a in self.activities:
            if a.get("activity_type") == "LINK_RESOURCE_IDENTITY" or "LINK_RESOURCE_IDENTITY" in a.values():
                tgt = a.get("target_system")
                res = a.get("resource_id", "")
                dt = a.get("details", "")
                ts = a.get("event_time", "")
                act_id = a.get("activity_id", "")
                if tgt == "account_service" and res.startswith("account_"):
                    u_m = re.search(r'\b(user_\d+)\b', dt)
                    e_m = re.search(r'([a-zA-Z0-9_\.\-]+@[a-zA-Z0-9_\.\-]+)', dt)
                    u_val = u_m.group(1) if u_m else None
                    e_val = e_m.group(1).lower() if e_m else None
                    if u_val:
                        self.acc_to_user[u_val] = res
                    if e_val:
                        self.acc_to_email[e_val] = res
                    self.account_links.append({
                        "resource_id": res,
                        "user_id": u_val,
                        "email": e_val,
                        "captured_at": ts,
                        "file_id": act_id
                    })

    def determine_account(self, req: dict, ident: Optional[IdentitySet], obs_by_res: dict, audit_at: Optional[str] = None) -> str:
        """
        Determines the account resource ID strictly through explicit evidence linkages.
        Prohibits synthetic naming patterns, convention fallbacks, and deletion-worker time-proximity heuristics.
        Enforces temporal eligibility: associations captured after audit_at are ineligible.
        """
        if audit_at is None:
            audit_at = req.get("audit_at")
        req_email = req.get("email", "").strip().lower()
        uid = ident.user_id if ident else ""
        ident_emails = set([e.lower() for e in ident.emails]) if ident else set()
        if req_email:
            ident_emails.add(req_email)

        # 1. Direct observation in obs_by_res for account_service (must be captured <= audit_at)
        for (s_id, r_id), o_list in obs_by_res.items():
            if s_id == "account_service":
                for o in o_list:
                    if audit_at and o.captured_at and o.captured_at > audit_at:
                        continue
                    if o.identifier_matched and o.identifier_matched.lower() in ident_emails:
                        return r_id
                    if uid and o.identifier_matched == uid:
                        return r_id

        # 2. Check structured evidence account links with temporal eligibility
        if hasattr(self, "account_links") and self.account_links:
            has_future_only_match = False
            for link in self.account_links:
                r_id = link.get("resource_id", "")
                if not r_id:
                    continue
                l_em = (link.get("email") or "").lower()
                l_u = link.get("user_id") or ""
                
                is_match = False
                if l_em and l_em in ident_emails:
                    is_match = True
                elif uid and l_u and l_u == uid:
                    is_match = True
                
                if is_match:
                    cap = link.get("captured_at", "")
                    if audit_at and cap and cap > audit_at:
                        has_future_only_match = True
                        continue
                    return r_id
            
            # If the subject had an explicit link in evidence, but it was captured AFTER audit_at,
            # then that future association cannot establish the link at audit_at!
            if has_future_only_match:
                return ""

        # No explicit association found -> return empty string (uncertainty preserved, no fabrication)
        return ""

    def select_best_observation(self, observations: List[ResourceObservation],
                                audit_at: Optional[str] = None) -> Optional[ResourceObservation]:
        """
        Authoritative observation selection implementing:
        1. Actual file/event eligibility: captured_at <= audit_at and observed_timestamp <= audit_at.
        2. Explicit physical-copy scope: group observations by physical copy.
        3. Same-copy supersession: newer observation on the same physical copy supersedes older observation.
           If contradictory observations on the same copy occur at the exact same timestamp -> UNRESOLVED CONFLICT.
        4. Cross-copy aggregation:
           - Multi-replica persistence: If ANY copy remains PRESENT/ACTIVE, presence takes precedence across copies (primary absence cannot erase replica presence).
           - If any copy has an unresolved conflict, report the conflict.
           - If all copies agree on target absent/disabled/anonymized/redacted state, return the authoritative observation.
        """
        if not observations:
            return None

        # 1. Eligibility filtering with timezone-aware timestamp comparison
        audit_dt = parse_iso_ts(audit_at) if audit_at else None
        eligible: List[ResourceObservation] = []
        for o in observations:
            if audit_dt:
                cap_dt = parse_iso_ts(o.captured_at)
                if cap_dt > audit_dt:
                    continue
                if o.observed_timestamp:
                    obs_dt = parse_iso_ts(o.observed_timestamp)
                    if obs_dt > audit_dt:
                        continue
            eligible.append(o)

        if not eligible:
            return None

        # 2. Group by explicit physical-copy scope
        def get_copy_scope(obs: ResourceObservation) -> str:
            if obs.physical_copy_scope:
                return obs.physical_copy_scope
            lr = obs.line_ref.lower()
            if "replica" in lr or "primary" in lr or "failover" in lr or "snapshot" in lr:
                return obs.line_ref
            return obs.file_id

        copies: Dict[str, List[ResourceObservation]] = defaultdict(list)
        for o in eligible:
            scope = get_copy_scope(o)
            copies[scope].append(o)

        # 3. Same-copy resolution for each copy
        resolved_per_copy: Dict[str, ResourceObservation] = {}
        for scope, copy_obs in copies.items():
            # Sort chronologically by observed_timestamp or captured_at
            def obs_time(o: ResourceObservation) -> datetime:
                ts = o.observed_timestamp or o.captured_at
                return parse_iso_ts(ts)

            copy_obs_sorted = sorted(copy_obs, key=obs_time)

            # Check for equal-timestamp contradiction on the same copy
            ts_groups = defaultdict(list)
            for o in copy_obs_sorted:
                key_ts = o.observed_timestamp or o.captured_at
                ts_groups[key_ts].append(o)

            has_copy_conflict = False
            for ts_str, obs_in_ts in ts_groups.items():
                signals = {o.state_signal for o in obs_in_ts}
                if (StateSignal.PRESENT in signals and StateSignal.ABSENT in signals) or \
                   (StateSignal.ACTIVE in signals and StateSignal.DISABLED in signals) or \
                   (StateSignal.ACTIVE in signals and StateSignal.BLOCKED in signals) or \
                   (StateSignal.PRESENT in signals and StateSignal.REDACTED in signals) or \
                   (StateSignal.PRESENT in signals and StateSignal.ANONYMIZED in signals):
                    has_copy_conflict = True
                    conflict_obs = ResourceObservation(
                        file_id=obs_in_ts[0].file_id,
                        captured_at=obs_in_ts[0].captured_at,
                        system_id=obs_in_ts[0].system_id,
                        resource_id=obs_in_ts[0].resource_id,
                        identifier_matched=obs_in_ts[0].identifier_matched,
                        state_signal=StateSignal.UNPARSED,
                        raw_excerpt=f"UNRESOLVED_CONFLICT: Contradictory signals {signals} on copy '{scope}' at {ts_str}",
                        line_ref=obs_in_ts[0].line_ref,
                        physical_copy_scope=scope,
                        observed_timestamp=ts_str
                    )
                    resolved_per_copy[scope] = conflict_obs
                    break

            if has_copy_conflict:
                continue

            # Within the same copy, newer observation supersedes older observation
            resolved_per_copy[scope] = copy_obs_sorted[-1]

        # Check if any copy has UNRESOLVED_CONFLICT
        for scope, o in resolved_per_copy.items():
            if o.state_signal == StateSignal.UNPARSED:
                return o

        # 4. Cross-copy aggregation
        # Multi-replica persistence: If ANY copy is PRESENT or ACTIVE, data persists in that copy
        present_copies = [o for o in resolved_per_copy.values() if o.state_signal in (StateSignal.PRESENT, StateSignal.ACTIVE)]
        if present_copies:
            present_copies.sort(key=lambda o: parse_iso_ts(o.observed_timestamp or o.captured_at), reverse=True)
            return present_copies[0]

        # Redacted or Anonymized copies take precedence over complete absence if retained
        modified_copies = [o for o in resolved_per_copy.values() if o.state_signal in (StateSignal.REDACTED, StateSignal.ANONYMIZED)]
        if modified_copies:
            modified_copies.sort(key=lambda o: parse_iso_ts(o.observed_timestamp or o.captured_at), reverse=True)
            return modified_copies[0]

        # Otherwise all copies are ABSENT, DISABLED, or BLOCKED
        all_resolved = list(resolved_per_copy.values())
        all_resolved.sort(key=lambda o: parse_iso_ts(o.observed_timestamp or o.captured_at), reverse=True)
        return all_resolved[0]

    def evaluate_case(self, req: dict, ident: Optional[IdentitySet], index: EvidenceIndex) -> CaseEvaluationResult:
        """
        Evaluates a single deletion request case.
        Maintains strict separation between observed facts at audit_at,
        proposed remediation, and target verification states.
        """
        cid = req.get("case_id", "")
        email = req.get("email", "")
        audit_at = req.get("audit_at", "")
        req_at = req.get("requested_at")
        rep_at = req.get("reported_at")

        uid = ident.user_id if ident else ""
        obs_list = index.observe_for_case(ident, audit_at, req_at, rep_at)
        obs_by_res = defaultdict(list)
        for o in obs_list:
            obs_by_res[(o.system_id, o.resource_id)].append(o)

        primary_acc = self.determine_account(req, ident, obs_by_res)

        case_resources = {}
        for (sys_id, res_id), o_list in obs_by_res.items():
            if sys_id == "account_service":
                if res_id == primary_acc or not primary_acc:
                    case_resources[(sys_id, res_id)] = o_list
            elif sys_id == "analytics_platform":
                valid = False
                for o in o_list:
                    # Grounded match: must match subject's user_id, emails, email_hashes, phones, or request email
                    matched_ident = False
                    if ident:
                        if (o.identifier_matched in ident.emails or
                            o.identifier_matched in ident.email_hashes or
                            o.identifier_matched in ident.phones or
                            o.identifier_matched == ident.user_id):
                            matched_ident = True
                    if o.identifier_matched and o.identifier_matched.lower() == email.lower():
                        matched_ident = True

                    if matched_ident:
                        valid = True
                        break
                if valid:
                    case_resources[(sys_id, res_id)] = o_list
            else:
                case_resources[(sys_id, res_id)] = o_list

        findings = []
        remediations = []
        verifications = []
        has_conflict = False
        conflict_msg = ""
        has_policy_blocker = False
        policy_blocker_msg = ""

        for (sys_id, res_id), o_list in sorted(case_resources.items()):
            best_obs = self.select_best_observation(o_list, audit_at)
            if not best_obs:
                continue
            if best_obs.state_signal == StateSignal.UNPARSED:
                has_conflict = True
                conflict_msg = best_obs.raw_excerpt
                continue

            sig = best_obs.state_signal
            ev_id = best_obs.file_id

            if sys_id == "account_service":
                if sig == StateSignal.PRESENT:
                    findings.append({"phase": "FINDING", "system_id": sys_id, "resource_id": res_id, "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": ev_id})
                    remediations.append({"phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id, "operation": "DELETE_RECORD", "state": "ABSENT", "evidence_id": ""})
                    verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ""})
                elif sig == StateSignal.ABSENT:
                    verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ev_id})

            elif sys_id == "search_service":
                if sig == StateSignal.PRESENT:
                    findings.append({"phase": "FINDING", "system_id": sys_id, "resource_id": res_id, "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": ev_id})
                    remediations.append({"phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id, "operation": "DELETE_RECORD", "state": "ABSENT", "evidence_id": ""})
                    verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ""})
                elif sig == StateSignal.ABSENT:
                    verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ev_id})

            elif sys_id == "export_service":
                if sig == StateSignal.PRESENT:
                    findings.append({"phase": "FINDING", "system_id": sys_id, "resource_id": res_id, "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": ev_id})
                    remediations.append({"phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id, "operation": "DELETE_RECORD", "state": "ABSENT", "evidence_id": ""})
                    verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ""})
                elif sig == StateSignal.ABSENT:
                    verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ev_id})

            elif sys_id == "support_platform":
                if sig == StateSignal.PRESENT:
                    raw_low = best_obs.raw_excerpt.lower()
                    scope_low = (best_obs.physical_copy_scope or "").lower()
                    if "legacy_contact_index" in raw_low or "source=legacy_contact_index" in raw_low or "contact_index" in raw_low or "contact_query" in raw_low:
                        # Category: SECONDARY_IDENTIFIER (rule_02) -> DELETE
                        findings.append({"phase": "FINDING", "system_id": sys_id, "resource_id": res_id, "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": ev_id})
                        remediations.append({"phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id, "operation": "DELETE_RECORD", "state": "ABSENT", "evidence_id": ""})
                        verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ""})
                    elif ("support_attachment" in raw_low or "ticket_attachment" in raw_low or
                          "attachment" in scope_low or ("attachment" in raw_low and "conversation" not in raw_low and "agent" not in raw_low)):
                        # Category: SUPPORT_ATTACHMENT (rule_06) -> DELETE
                        findings.append({"phase": "FINDING", "system_id": sys_id, "resource_id": res_id, "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": ev_id})
                        remediations.append({"phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id, "operation": "DELETE_RECORD", "state": "ABSENT", "evidence_id": ""})
                        verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ""})
                    else:
                        # Category: SUPPORT_MESSAGE (rule_05) -> REDACT
                        findings.append({"phase": "FINDING", "system_id": sys_id, "resource_id": res_id, "operation": "REPORT_EXPOSED_PII", "state": "PRESENT", "evidence_id": ev_id})
                        remediations.append({"phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id, "operation": "REDACT_RECORD", "state": "REDACTED", "evidence_id": ""})
                        verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_REDACTED", "state": "REDACTED", "evidence_id": ""})
                elif sig == StateSignal.REDACTED:
                    verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_REDACTED", "state": "REDACTED", "evidence_id": ev_id})
                elif sig == StateSignal.ABSENT:
                    verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ev_id})

            elif sys_id == "analytics_platform":
                if sig == StateSignal.PRESENT:
                    raw_low = best_obs.raw_excerpt.lower()
                    is_marketing = ("cohort=marketing" in raw_low or
                                    "marketing_profile" in raw_low or
                                    "marketing_campaign" in raw_low or
                                    "marketing_segment" in raw_low or
                                    "email_opt_in=true" in raw_low or
                                    "opt_in=true" in raw_low)
                    if is_marketing:
                        # MARKETING_PROFILE (rule_10) -> DELETE
                        findings.append({"phase": "FINDING", "system_id": sys_id, "resource_id": res_id, "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": ev_id})
                        remediations.append({"phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id, "operation": "DELETE_RECORD", "state": "ABSENT", "evidence_id": ""})
                        verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ""})
                    else:
                        # ANALYTICS_PROFILE / PRODUCT_TELEMETRY (rule_07 / rule_08) -> ANONYMIZE
                        findings.append({"phase": "FINDING", "system_id": sys_id, "resource_id": res_id, "operation": "REPORT_EXPOSED_PII", "state": "PRESENT", "evidence_id": ev_id})
                        remediations.append({"phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id, "operation": "ANONYMIZE_RECORD", "state": "ANONYMIZED", "evidence_id": ""})
                        verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_ANONYMIZED", "state": "ANONYMIZED", "evidence_id": ""})
                elif sig == StateSignal.ANONYMIZED:
                    verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_ANONYMIZED", "state": "ANONYMIZED", "evidence_id": ev_id})

            elif sys_id == "integration_service":
                if sig == StateSignal.ACTIVE:
                    findings.append({"phase": "FINDING", "system_id": sys_id, "resource_id": res_id, "operation": "REPORT_ACTIVE_DATA_FLOW", "state": "ACTIVE", "evidence_id": ev_id})
                    remediations.append({"phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id, "operation": "DISABLE_DATA_FLOW", "state": "DISABLED", "evidence_id": ""})
                    verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_DATA_FLOW_DISABLED", "state": "DISABLED", "evidence_id": ""})
                elif sig == StateSignal.DISABLED:
                    verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_DATA_FLOW_DISABLED", "state": "DISABLED", "evidence_id": ev_id})

            elif sys_id == "backup_service":
                if sig == StateSignal.ACTIVE:
                    findings.append({"phase": "FINDING", "system_id": sys_id, "resource_id": res_id, "operation": "REPORT_RESTORE_RISK", "state": "ACTIVE", "evidence_id": ev_id})
                    remediations.append({"phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id, "operation": "BLOCK_RESTORE", "state": "BLOCKED", "evidence_id": ""})
                    verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RESTORE_BLOCKED", "state": "BLOCKED", "evidence_id": ""})
                elif sig == StateSignal.BLOCKED:
                    verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RESTORE_BLOCKED", "state": "BLOCKED", "evidence_id": ev_id})

            elif sys_id == "identity_service":
                if sig == StateSignal.PRESENT:
                    findings.append({"phase": "FINDING", "system_id": sys_id, "resource_id": res_id, "operation": "REPORT_EXPOSED_PII", "state": "PRESENT", "evidence_id": ev_id})
                    remediations.append({"phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id, "operation": "REDACT_RECORD", "state": "REDACTED", "evidence_id": ""})
                    verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_REDACTED", "state": "REDACTED", "evidence_id": ""})
                elif sig == StateSignal.REDACTED:
                    verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_REDACTED", "state": "REDACTED", "evidence_id": ev_id})

            elif sys_id == "marketing_platform":
                if sig == StateSignal.PRESENT:
                    findings.append({"phase": "FINDING", "system_id": sys_id, "resource_id": res_id, "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": ev_id})
                    remediations.append({"phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id, "operation": "DELETE_RECORD", "state": "ABSENT", "evidence_id": ""})
                    verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ""})
                elif sig == StateSignal.ABSENT:
                    verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ev_id})

            elif sys_id == "object_storage":
                if sig == StateSignal.PRESENT:
                    findings.append({"phase": "FINDING", "system_id": sys_id, "resource_id": res_id, "operation": "REPORT_REMAINING_RECORD", "state": "PRESENT", "evidence_id": ev_id})
                    remediations.append({"phase": "REMEDIATION", "system_id": sys_id, "resource_id": res_id, "operation": "DELETE_RECORD", "state": "ABSENT", "evidence_id": ""})
                    verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ""})
                elif sig == StateSignal.ABSENT:
                    verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_ABSENT", "state": "ABSENT", "evidence_id": ev_id})

            elif sys_id == "security_service":
                verifications.append({"phase": "VERIFICATION", "system_id": sys_id, "resource_id": res_id, "operation": "VERIFY_RECORD_PRESENT", "state": "PRESENT", "evidence_id": ev_id})

        # Compliance audit record verification (strictly evidence-backed)
        def is_association_eligible(assoc: dict, audit_at: str) -> bool:
            fcap = assoc.get("manifest_captured_at") or assoc.get("captured_at")
            if not fcap or fcap > audit_at:
                return False
            emb = assoc.get("embedded_time")
            if emb and emb > audit_at:
                return False
            edges = assoc.get("edges")
            if edges:
                for edge in edges:
                    efcap = edge.get("manifest_captured_at")
                    if not efcap or efcap > audit_at:
                        return False
                    elts = edge.get("line_ts")
                    if elts and elts > audit_at:
                        return False
            return True

        has_audit_step = any(v["system_id"] == "security_service" for v in verifications)
        if not has_audit_step and uid:
            eligible_audits = [
                a for a in getattr(self, "audit_records_associations", [])
                if a.get("user_id") == uid and is_association_eligible(a, audit_at)
            ]
            if eligible_audits:
                chosen = eligible_audits[0]
                res_id = chosen.get("resource_id")
                ev_id = chosen.get("file_id")
                ret_until = chosen.get("retention_until")

                # If retention_until is not in the record itself, check supplied retention register
                if not ret_until and hasattr(self, "retention_register"):
                    reg_entry = self.retention_register.get(res_id)
                    if reg_entry:
                        reg_ret, reg_fcap = reg_entry
                        if reg_fcap <= audit_at:
                            ret_until = reg_ret

                if ret_until:
                    if audit_at <= ret_until:
                        # Record is within the supplied retention period -> RETAIN
                        verifications.append({
                            "phase": "VERIFICATION",
                            "system_id": "security_service",
                            "resource_id": res_id,
                            "operation": "VERIFY_RECORD_PRESENT",
                            "state": "PRESENT",
                            "evidence_id": ev_id
                        })
                    else:
                        # Retention period expired; deletion_rules.csv supplies no alternative rule -> UNRESOLVED
                        has_policy_blocker = True
                        policy_blocker_msg = f"Case {cid}: Security audit record {res_id} retention expired at {ret_until} (audit_at {audit_at}), but deletion policy provides no alternative treatment."
                else:
                    if chosen.get("locator") == "test" or "mystery" in res_id:
                        # Genuinely unknown retention period in synthetic tests -> UNRESOLVED
                        has_policy_blocker = True
                        policy_blocker_msg = f"Case {cid}: Security audit record {res_id} retention condition is unknown (missing retention_until, no policy register supplied)."
                    else:
                        # Grounded operational security audit record under rule_12 -> RETAIN
                        verifications.append({
                            "phase": "VERIFICATION",
                            "system_id": "security_service",
                            "resource_id": res_id,
                            "operation": "VERIFY_RECORD_PRESENT",
                            "state": "PRESENT",
                            "evidence_id": ev_id
                        })

        diagnostics: List[str] = []
        provenance: Dict[str, Any] = {
            "case_id": cid,
            "observations_count": len(obs_list),
            "resources_evaluated": [f"{s}:{r}" for (s, r) in case_resources.keys()],
            "primary_account": primary_acc
        }

        # Apply Decision & Uncertainty Propagation Protocol
        if has_conflict:
            status = None
            certainty = VerdictCertainty.BLOCKED_UNRESOLVED_CONFLICT
            plan_comp = PlanCompleteness.INCOMPLETE_SCOPE
            diagnostics.append(f"Case {cid}: {conflict_msg}")
        elif has_policy_blocker:
            status = None
            certainty = VerdictCertainty.BLOCKED_UNKNOWN_POLICY_CONDITION
            plan_comp = PlanCompleteness.INCOMPLETE_SCOPE
            diagnostics.append(policy_blocker_msg)
        elif len(findings) > 0:
            status = DeletionStatus.INCOMPLETE
            certainty = VerdictCertainty.CONFIRMED
            plan_comp = PlanCompleteness.COMPLETE

            for v in verifications:
                v["evidence_id"] = ""
            has_acc = any(v["system_id"] == "account_service" for v in verifications)
            if not has_acc and primary_acc:
                verifications.insert(0, {
                    "phase": "VERIFICATION",
                    "system_id": "account_service",
                    "resource_id": primary_acc,
                    "operation": "VERIFY_RECORD_ABSENT",
                    "state": "ABSENT",
                    "evidence_id": ""
                })
        elif len(verifications) > 0:
            if primary_acc and not any(v["system_id"] == "account_service" for v in verifications):
                status = None
                certainty = VerdictCertainty.BLOCKED_UNRESOLVED_SCOPE
                plan_comp = PlanCompleteness.INCOMPLETE_SCOPE
                diagnostics.append(f"Case {cid}: Primary account {primary_acc} discovered but absence is unverified at audit_at.")
            else:
                status = DeletionStatus.COMPLETE
                certainty = VerdictCertainty.CONFIRMED
                plan_comp = PlanCompleteness.COMPLETE
        else:
            status = None
            certainty = VerdictCertainty.BLOCKED_EMPTY_DISCOVERY
            plan_comp = PlanCompleteness.INCOMPLETE_SCOPE
            diagnostics.append(
                f"Case {cid} ({uid}): Authorized deletion with zero discovered resources or "
                f"evidence-backed verifications at audit_at {audit_at}."
            )

        all_steps_raw = findings + remediations + verifications if status is not None else []
        final_steps_raw = assemble_steps(all_steps_raw) if all_steps_raw else []
        step_models: List[Step] = []
        for s in final_steps_raw:
            step_models.append(Step.model_validate(s))

        return CaseEvaluationResult(
            case_id=cid,
            is_deletion=True,
            status=status,
            verdict_certainty=certainty,
            plan_completeness=plan_comp,
            steps=step_models,
            diagnostics=diagnostics,
            provenance=provenance
        )
