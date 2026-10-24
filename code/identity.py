"""
Identity resolution module for HackerRank Orchestrate (October 2026)
Ghost Data Still Exists

Reconstructs current and historical user identifiers at or before audit_at.
Replays user_audit_log backwards from user_identities snapshot:
- Events after audit_at are rolled back and excluded from the pre-audit IdentitySet.
- Events at or before audit_at contribute historical identifiers.
"""

from __future__ import annotations
import os
import csv
import hashlib
from datetime import datetime
from typing import Dict, List, Set, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(REPO_ROOT, "dataset")


def compute_email_hash(email: str) -> str:
    """Compute normalized SHA-256 hash of an email address."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


class IdentitySet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str
    name: str
    emails: frozenset[str]
    email_hashes: frozenset[str]
    phones: frozenset[str]
    active_email: str
    active_email_hash: str
    active_phone: str


class IdentityManager:
    """Caches and resolves identity snapshots and historical audit trajectories."""

    def __init__(self, dataset_dir: str = DATASET_DIR):
        self.dataset_dir = dataset_dir
        self.users: Dict[str, dict] = {}
        self.user_audit_logs: Dict[str, List[dict]] = {}
        self.current_email_to_uid: Dict[str, str] = {}
        self.hist_email_to_uid: Dict[str, str] = {}
        self._load()

    def _load(self):
        identities_path = os.path.join(self.dataset_dir, "user_identities.csv")
        audit_path = os.path.join(self.dataset_dir, "user_audit_log.csv")

        with open(identities_path, "r", encoding="utf-8", errors="replace") as f:
            for r in csv.DictReader(f):
                uid = r["user_id"]
                self.users[uid] = r
                self.current_email_to_uid[r["email"].strip().lower()] = uid

        with open(audit_path, "r", encoding="utf-8", errors="replace") as f:
            for r in csv.DictReader(f):
                uid = r["user_id"]
                self.user_audit_logs.setdefault(uid, []).append(r)
                if r["field_name"] == "email":
                    old_em = r["old_value"].strip().lower()
                    new_em = r["new_value"].strip().lower()
                    self.hist_email_to_uid[old_em] = uid
                    self.hist_email_to_uid[new_em] = uid

        # Sort audit logs descending by event_time for backward replay
        for uid in self.user_audit_logs:
            self.user_audit_logs[uid].sort(key=lambda x: x["event_time"], reverse=True)

    def find_user_id(self, email: str) -> Optional[str]:
        norm = email.strip().lower()
        if norm in self.current_email_to_uid:
            return self.current_email_to_uid[norm]
        if norm in self.hist_email_to_uid:
            return self.hist_email_to_uid[norm]
        return None

    def resolve(self, request_email: str, audit_at: Union[datetime, str]) -> Optional[IdentitySet]:
        uid = self.find_user_id(request_email)
        if not uid or uid not in self.users:
            return None

        if isinstance(audit_at, datetime):
            audit_at_str = audit_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            audit_at_str = str(audit_at)

        user_row = self.users[uid]
        name = user_row["name"]

        # Current snapshot values
        current_email = user_row["email"].strip().lower()
        current_phone = user_row["phone"].strip()

        # Audit history for this user
        audits = self.user_audit_logs.get(uid, [])

        # Backward replay from snapshot
        # 1. Any change with event_time > audit_at occurred in the FUTURE relative to audit_at.
        # We roll back the active value to old_value, and DO NOT include new_value in pre-audit identity.
        active_email = current_email
        active_phone = current_phone

        valid_emails: Set[str] = set()
        valid_phones: Set[str] = set()

        # We first process post-audit changes backwards
        for a in audits:
            etime = a["event_time"]
            field = a["field_name"]
            old_val = a["old_value"].strip()
            new_val = a["new_value"].strip()

            if etime > audit_at_str:
                # Post-audit change: rollback active state
                if field == "email":
                    if active_email == new_val.lower():
                        active_email = old_val.lower()
                elif field == "phone":
                    if active_phone == new_val:
                        active_phone = old_val
            else:
                # Event happened at or before audit_at
                # Both old_val and new_val were valid at or before audit_at
                if field == "email":
                    valid_emails.add(old_val.lower())
                    valid_emails.add(new_val.lower())
                elif field == "phone":
                    valid_phones.add(old_val)
                    valid_phones.add(new_val)

        # The active value at audit_at is guaranteed valid
        valid_emails.add(active_email)
        valid_phones.add(active_phone)

        # Generate hashes for all valid emails
        valid_hashes = {compute_email_hash(em) for em in valid_emails}
        active_email_hash = compute_email_hash(active_email)

        return IdentitySet(
            user_id=uid,
            name=name,
            emails=frozenset(valid_emails),
            email_hashes=frozenset(valid_hashes),
            phones=frozenset(valid_phones),
            active_email=active_email,
            active_email_hash=active_email_hash,
            active_phone=active_phone
        )


_default_manager: Optional[IdentityManager] = None


def get_identity_manager(dataset_dir: str = DATASET_DIR) -> IdentityManager:
    global _default_manager
    if _default_manager is None or _default_manager.dataset_dir != dataset_dir:
        _default_manager = IdentityManager(dataset_dir)
    return _default_manager


def resolve_identity(request_or_email: Union[str, dict], audit_at: Union[datetime, str], dataset_dir: str = DATASET_DIR) -> Optional[IdentitySet]:
    mgr = get_identity_manager(dataset_dir)
    if isinstance(request_or_email, dict):
        email = request_or_email.get("email", "")
    else:
        email = str(request_or_email)
    return mgr.resolve(email, audit_at)
