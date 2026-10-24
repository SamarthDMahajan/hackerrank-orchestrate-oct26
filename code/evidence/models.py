"""
Evidence observation models for HackerRank Orchestrate (October 2026)
Ghost Data Still Exists.
"""

from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class StateSignal(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    REDACTED = "REDACTED"
    ANONYMIZED = "ANONYMIZED"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"
    UNPARSED = "UNPARSED"


class ResourceObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    file_id: str
    captured_at: str
    system_id: str
    resource_id: str
    identifier_matched: str
    state_signal: StateSignal
    raw_excerpt: str
    line_ref: str
