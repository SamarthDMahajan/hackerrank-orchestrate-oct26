"""
Visual evidence parser for HackerRank Orchestrate (October 2026).
Ingests verified VisualSidecar assets from data/visual_sidecars/ backed by
raw pixel and PDF stream inspection with full SHA-256 fingerprint verification.

Quarantines and replaces the unverified IMAGE_EVIDENCE_CATALOG fallback dictionary.
"""

from __future__ import annotations
import os
import hashlib
from typing import List, Optional, Set
from .models import ResourceObservation, StateSignal
from .sidecar_models import VisualSidecar, SidecarRecord
from code.identity import IdentitySet

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_SIDECAR_DIR = os.path.join(REPO_ROOT, "data", "visual_sidecars")
if not os.path.exists(DEFAULT_SIDECAR_DIR):
    alt_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "visual_sidecars")
    if os.path.exists(alt_dir):
        DEFAULT_SIDECAR_DIR = alt_dir


def compute_file_sha256(file_path: str) -> str:
    """Computes the full SHA-256 hash of a file on disk."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def parse_visual_evidence(
    file_path: str,
    file_id: str,
    captured_at: str,
    identity: Optional[IdentitySet],
    candidate_resources: Optional[Set[str]] = None,
    sidecar_dir: Optional[str] = None,
    audit_at: Optional[str] = None
) -> List[ResourceObservation]:
    """
    Ingests visual observations from a verified sidecar asset.
    Validates:
    1. Sidecar file existence in sidecar_dir.
    2. Strict schema conformance via VisualSidecar.
    3. Source evidence ID matching file_id.
    4. Exact source SHA-256 fingerprint match against file_path on disk.
    5. Temporal eligibility: sidecar captured_at <= audit_at, and record observed_timestamp <= audit_at.
    6. Row-level subject association: exact matching of user_id, emails, or phones, or candidate resource.
    """
    observations: List[ResourceObservation] = []
    resolved_sidecar_dir = sidecar_dir or DEFAULT_SIDECAR_DIR
    sidecar_path = os.path.join(resolved_sidecar_dir, f"{file_id}.json")

    if not os.path.exists(sidecar_path):
        # Missing sidecar: cannot invent or guess observations
        return observations

    # 1. Load and validate sidecar schema
    with open(sidecar_path, "r", encoding="utf-8") as f:
        raw_json = f.read()

    sidecar = VisualSidecar.model_validate_json(raw_json)

    # 2. Verify evidence ID
    if sidecar.evidence_id != file_id:
        raise ValueError(f"Sidecar evidence_id mismatch: expected {file_id}, got {sidecar.evidence_id}")

    # 3. Resolve disk source file and verify SHA-256 fingerprint
    target_file = file_path
    if not os.path.exists(target_file):
        cand = os.path.join(REPO_ROOT, "dataset", sidecar.file_path.replace("/", os.sep))
        if os.path.exists(cand):
            target_file = cand

    if not os.path.exists(target_file):
        return observations

    disk_sha256 = compute_file_sha256(target_file)
    if sidecar.source_sha256 != disk_sha256:
        raise ValueError(
            f"Source SHA-256 fingerprint mismatch for {file_id}: "
            f"sidecar={sidecar.source_sha256}, disk={disk_sha256}"
        )

    # 4. Check temporal eligibility of the capture
    if audit_at and sidecar.captured_at > audit_at:
        return observations

    if not identity:
        return observations

    user_id_clean = identity.user_id.strip().lower() if identity.user_id else ""
    user_emails = {em.strip().lower() for em in identity.emails}
    user_phones = {ph.strip() for ph in identity.phones}
    user_name = identity.name.strip().lower() if identity.name else ""

    # 5. Process observed records
    for rec in sidecar.observed_records:
        # Check record-level observation timestamp if present
        if audit_at and rec.observed_timestamp and rec.observed_timestamp > audit_at:
            # Embedded event occurred after audit_at -> ineligible
            continue

        matched_id = None
        for ident in rec.visible_identifiers:
            ident_clean = ident.strip().lower()
            if user_id_clean and ident_clean == user_id_clean:
                matched_id = identity.user_id
                break
            if ident_clean in user_emails:
                matched_id = ident
                break
            if ident.strip() in user_phones:
                matched_id = ident
                break
            if user_name and ident_clean == user_name:
                matched_id = identity.user_id
                break

        # Check candidate resource association if not matched by identifier
        if not matched_id and candidate_resources and rec.resource_id:
            if rec.resource_id in candidate_resources:
                matched_id = rec.resource_id

        if matched_id:
            locator_ref = f"{sidecar.file_path}:{rec.locator}"
            observations.append(ResourceObservation(
                file_id=sidecar.evidence_id,
                captured_at=sidecar.captured_at,
                system_id=rec.system_id,
                resource_id=rec.resource_id or "",
                identifier_matched=matched_id,
                state_signal=rec.state_signal,
                raw_excerpt=rec.raw_excerpt,
                line_ref=locator_ref
            ))

    return observations


def parse_image(
    file_path: str,
    file_id: str,
    captured_at: str,
    identity: Optional[IdentitySet],
    candidate_resources: Optional[Set[str]] = None,
    sidecar_dir: Optional[str] = None,
    audit_at: Optional[str] = None
) -> List[ResourceObservation]:
    """
    Backwards-compatible wrapper delegating to parse_visual_evidence.
    """
    return parse_visual_evidence(
        file_path=file_path,
        file_id=file_id,
        captured_at=captured_at,
        identity=identity,
        candidate_resources=candidate_resources,
        sidecar_dir=sidecar_dir,
        audit_at=audit_at
    )
