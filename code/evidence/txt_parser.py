"""
TXT evidence parser for HackerRank Orchestrate (October 2026).
Parses shift handover and text logs emitting ResourceObservations.
"""

from typing import List
from .models import ResourceObservation, StateSignal
from code.identity import IdentitySet

STATUS_MAP = {
    "NOT_FOUND": StateSignal.ABSENT,
    "ABSENT": StateSignal.ABSENT,
    "PRESENT": StateSignal.PRESENT,
    "EXPOSED_PII": StateSignal.PRESENT,
    "ACTIVE": StateSignal.ACTIVE,
    "DISABLED": StateSignal.DISABLED,
    "BLOCKED": StateSignal.BLOCKED,
    "REDACTED": StateSignal.REDACTED,
    "ANONYMIZED": StateSignal.ANONYMIZED
}


def parse_txt(file_path: str, file_id: str, captured_at: str, identity: IdentitySet) -> List[ResourceObservation]:
    observations = []
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line or not line.startswith("-"):
                continue

            parts = [p.strip() for p in line.lstrip("-").split("|")]
            if len(parts) < 6:
                continue

            ts, system_id, resource_id, category, status_raw, identifier = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]

            # Check if identifier matches IdentitySet
            ident_clean = identifier.strip().lower()
            matched = None
            if ident_clean == identity.user_id.lower():
                matched = identity.user_id
            elif ident_clean in identity.emails:
                matched = ident_clean
            elif ident_clean in identity.email_hashes:
                matched = ident_clean
            elif identifier.strip() in identity.phones:
                matched = identifier.strip()

            if matched:
                state_signal = STATUS_MAP.get(status_raw.upper(), StateSignal.UNPARSED)
                observations.append(ResourceObservation(
                    file_id=file_id,
                    captured_at=captured_at,
                    system_id=system_id,
                    resource_id=resource_id,
                    identifier_matched=matched,
                    state_signal=state_signal,
                    raw_excerpt=line[:300],
                    line_ref=str(line_no)
                ))

    return observations
