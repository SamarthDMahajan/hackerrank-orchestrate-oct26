"""
Strict Pydantic models for visual evidence sidecars.
HackerRank Orchestrate (October 2026) - Ghost Data Still Exists.
"""

from __future__ import annotations
from typing import List, Optional, Dict
from pydantic import BaseModel, ConfigDict, Field
from .models import StateSignal


class SidecarRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    locator: str
    system_id: str
    resource_id: Optional[str] = None
    visible_identifiers: List[str] = Field(default_factory=list)
    state_signal: StateSignal
    observed_timestamp: Optional[str] = None
    raw_excerpt: str
    physical_copy_scope: Optional[str] = None
    notes: Optional[str] = None


class VisualSidecar(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: str = "1.0.0"
    evidence_id: str
    file_path: str
    source_sha256: str
    captured_at: str
    extraction_tool: str
    extraction_timestamp: str
    review_status: str
    media_type: str
    dimensions: Optional[Dict[str, int]] = None
    page_count: Optional[int] = None
    coverage: str
    literal_transcription: str
    observed_records: List[SidecarRecord] = Field(default_factory=list)
