"""
Evidence indexer and aggregator for HackerRank Orchestrate (October 2026)
Ghost Data Still Exists.

Enforces temporal boundary: captured_at <= audit_at (inclusive).
Confirmed by AGENTS.md:209:
"Use only information available at or before audit_at when deciding the case. Evidence created later must not change the answer for that case."
"""

import os
import csv
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from .models import ResourceObservation, StateSignal
from .json_parser import parse_json
from .log_parser import parse_log
from .sql_parser import parse_sql
from .txt_parser import parse_txt
from .pdf_parser import parse_pdf
from code.identity import IdentitySet

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATASET_DIR = os.path.join(REPO_ROOT, "dataset")


class EvidenceIndex:
    def __init__(self, dataset_dir: str = DATASET_DIR):
        self.dataset_dir = dataset_dir
        self.manifest: List[dict] = []
        self.activities: List[dict] = []
        self._load_manifest()
        self._load_activities()

    def _load_manifest(self):
        mpath = os.path.join(self.dataset_dir, "evidence_files.csv")
        with open(mpath, "r", encoding="utf-8", errors="replace") as f:
            self.manifest = list(csv.DictReader(f))

    def _load_activities(self):
        act_path = os.path.join(self.dataset_dir, "system_activity.csv")
        if os.path.exists(act_path):
            with open(act_path, "r", encoding="utf-8", errors="replace") as f:
                self.activities = list(csv.DictReader(f))

    def get_eligible_files(self, audit_at: str) -> List[dict]:
        """
        Filters evidence files captured at or before case audit_at.
        Boundary: captured_at <= audit_at (inclusive).
        """
        eligible = []
        for e in self.manifest:
            c_at = e.get("captured_at", "")
            if c_at <= audit_at:
                eligible.append(e)
        return eligible

    def get_candidate_resources(self, identity: IdentitySet, audit_at: str,
                                requested_at: Optional[str] = None,
                                reported_at: Optional[str] = None) -> set:
        candidates = set()
        # Account ID convention for users: user_01 -> account_001, account_1
        num_str = "".join(ch for ch in identity.user_id if ch.isdigit())
        if num_str:
            candidates.add(f"account_{num_str}")
            candidates.add(f"account_{num_str.zfill(3)}")
            try:
                candidates.add(f"account_{int(num_str)}")
            except ValueError:
                pass

        # Filter activities at or before audit_at
        eligible_acts = [a for a in self.activities if a.get("event_time", "") <= audit_at]

        # Activities directly naming user or emails
        for a in eligible_acts:
            a_res = a.get("resource_id")
            if not a_res:
                continue
            a_text = f"{a.get('details', '')} {a.get('resource_id', '')}"
            if identity.user_id in a_text or any(em in a_text for em in identity.emails):
                candidates.add(a_res)

        # Deletion worker window around reported_at
        if reported_at:
            try:
                rep_dt = datetime.fromisoformat(reported_at.replace("Z", "+00:00"))
                for a in eligible_acts:
                    if a.get("source_system") == "deletion_worker":
                        a_time = a.get("event_time", "")
                        if a_time:
                            a_dt = datetime.fromisoformat(a_time.replace("Z", "+00:00"))
                            if abs((a_dt - rep_dt).total_seconds()) <= 7200:
                                candidates.add(a["resource_id"])
            except Exception:
                pass

        return candidates

    def observe_for_case(self, identity: IdentitySet, audit_at: str,
                         requested_at: Optional[str] = None,
                         reported_at: Optional[str] = None,
                         candidate_resources: Optional[set] = None) -> List[ResourceObservation]:
        """
        Parses all eligible evidence files for the case's IdentitySet at or before audit_at.
        """
        eligible_files = self.get_eligible_files(audit_at)
        all_observations: List[ResourceObservation] = []

        if candidate_resources is None:
            candidate_resources = self.get_candidate_resources(identity, audit_at, requested_at, reported_at)

        for e in eligible_files:
            fid = e["file_id"]
            fpath = os.path.join(self.dataset_dir, e["file_path"].replace("/", os.sep))
            cat = e["captured_at"]

            if not os.path.exists(fpath):
                continue

            ext = os.path.splitext(fpath)[1].lower()
            obs: List[ResourceObservation] = []

            if ext == ".json":
                obs = parse_json(fpath, fid, cat, identity, candidate_resources)
            elif ext == ".log":
                obs = parse_log(fpath, fid, cat, identity, candidate_resources)
            elif ext == ".sql":
                obs = parse_sql(fpath, fid, cat, identity, candidate_resources)
            elif ext == ".txt":
                obs = parse_txt(fpath, fid, cat, identity)
            elif ext == ".pdf":
                obs = parse_pdf(fpath, fid, cat, identity)

            all_observations.extend(obs)

        return all_observations

