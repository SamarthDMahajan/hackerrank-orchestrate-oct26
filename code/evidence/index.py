"""
Evidence indexer and aggregator for HackerRank Orchestrate (October 2026)
Ghost Data Still Exists.

Enforces temporal boundary: captured_at <= audit_at (inclusive).
Confirmed by AGENTS.md:209:
"Use only information available at or before audit_at when deciding the case. Evidence created later must not change the answer for that case."
"""

import os
import re
import csv
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from .models import ResourceObservation, StateSignal
from .json_parser import parse_json
from .log_parser import parse_log
from .sql_parser import parse_sql
from .txt_parser import parse_txt
from .pdf_parser import parse_pdf
from .image_parser import parse_image
from code.identity import IdentitySet

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATASET_DIR = os.path.join(REPO_ROOT, "dataset")


class EvidenceIndex:
    def __init__(self, dataset_dir: str = DATASET_DIR, sidecar_dir: Optional[str] = None):
        self.dataset_dir = dataset_dir
        if sidecar_dir is not None:
            self.sidecar_dir = sidecar_dir
        else:
            cand_sidecar = os.path.join(REPO_ROOT, "data", "visual_sidecars")
            if not os.path.exists(cand_sidecar):
                alt_sidecar = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "visual_sidecars")
                if os.path.exists(alt_sidecar):
                    cand_sidecar = alt_sidecar
            self.sidecar_dir = cand_sidecar
        self.manifest: List[dict] = []
        self.activities: List[dict] = []
        self.diagnostics: List[str] = []
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

    def get_eligible_files(self, audit_at: str, requested_at: Optional[str] = None) -> List[dict]:
        """
        Filters evidence files captured at or before case audit_at.
        Enforces upper cutoff: captured_at <= audit_at (inclusive).
        Global lower cutoff of requested_at is removed per contract to permit legitimate pre-request evidence.
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
        """
        Discovers candidate resources grounded exclusively in explicit identity matches
        from eligible activities at or before audit_at.
        Uses exact token and word-boundary matching to prevent substring collisions (e.g. user_1 vs user_10).
        """
        candidates = set()
        if not identity:
            return candidates

        eligible_acts = [a for a in self.activities if a.get("event_time", "") <= audit_at]

        for a in eligible_acts:
            a_res = a.get("resource_id")
            if not a_res:
                continue
            details = a.get("details", "")
            combined = f"{details} {a_res}".lower()
            tokens = set(re.split(r'[\s,;:\'\"=()<>{}\[\]]+', combined))

            matched = False
            if identity.user_id and identity.user_id.lower() in tokens:
                matched = True
            if not matched:
                for em in identity.emails:
                    if em and em.lower() in tokens:
                        matched = True
                        break
            if not matched:
                for h in identity.email_hashes:
                    if h and h.lower() in tokens:
                        matched = True
                        break
            if not matched:
                for ph in identity.phones:
                    if ph and ph in tokens:
                        matched = True
                        break
            if not matched:
                for em in identity.emails:
                    if em:
                        pattern = r'(?<![a-zA-Z0-9_\-\.])' + re.escape(em.lower()) + r'(?![a-zA-Z0-9_\-\.])'
                        if re.search(pattern, combined):
                            matched = True
                            break
            if not matched and identity.user_id:
                pattern = r'(?<![a-zA-Z0-9_])' + re.escape(identity.user_id.lower()) + r'(?![a-zA-Z0-9_])'
                if re.search(pattern, combined):
                    matched = True

            if matched:
                candidates.add(a_res)

        return candidates

    def observe_for_case(self, identity: IdentitySet, audit_at: str,
                         requested_at: Optional[str] = None,
                         reported_at: Optional[str] = None,
                         candidate_resources: Optional[set] = None) -> List[ResourceObservation]:
        """
        Parses all eligible evidence files for the case's IdentitySet at or before audit_at.
        """
        eligible_files = self.get_eligible_files(audit_at, requested_at)
        all_observations: List[ResourceObservation] = []

        if candidate_resources is None:
            candidate_resources = self.get_candidate_resources(identity, audit_at, requested_at, reported_at)

        for e in eligible_files:
            fid = e["file_id"]
            fpath = os.path.join(self.dataset_dir, e["file_path"].replace("/", os.sep))
            cat = e["captured_at"]

            if not os.path.exists(fpath):
                self.diagnostics.append(f"Missing evidence file for {fid} at path: {fpath}")
                continue

            ext = os.path.splitext(fpath)[1].lower()
            obs: List[ResourceObservation] = []

            try:
                if ext == ".json":
                    obs = parse_json(fpath, fid, cat, identity, candidate_resources)
                elif ext == ".log":
                    obs = parse_log(fpath, fid, cat, identity, candidate_resources)
                elif ext == ".sql":
                    obs = parse_sql(fpath, fid, cat, identity, candidate_resources)
                elif ext == ".txt":
                    obs = parse_txt(fpath, fid, cat, identity)
                elif ext == ".pdf":
                    obs = parse_pdf(fpath, fid, cat, identity, sidecar_dir=self.sidecar_dir, audit_at=audit_at)
                elif ext == ".png":
                    obs = parse_image(fpath, fid, cat, identity, candidate_resources, sidecar_dir=self.sidecar_dir, audit_at=audit_at)
            except Exception as ex:
                self.diagnostics.append(f"Parse failure for {fid} ({fpath}): {str(ex)}")

            all_observations.extend(obs)

        return all_observations

