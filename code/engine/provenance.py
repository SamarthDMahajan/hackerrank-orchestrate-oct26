"""
Typed provenance and evidence tracking models for HackerRank Orchestrate (October 2026).
Ghost Data Still Exists.
"""

from __future__ import annotations
from enum import Enum
from typing import Optional, Set, List
from pydantic import BaseModel, ConfigDict, Field
from code.evidence.models import StateSignal


class AssociationMethod(str, Enum):
    EXPLICIT_IDENTIFIER_MATCH = "EXPLICIT_IDENTIFIER_MATCH"
    LOG_TRACE_CORRELATION = "LOG_TRACE_CORRELATION"
    SQL_FOREIGN_KEY = "SQL_FOREIGN_KEY"
    HANDOVER_DOCUMENT = "HANDOVER_DOCUMENT"
    UNRESOLVED = "UNRESOLVED"


class PhysicalCopyScope(str, Enum):
    PRIMARY = "PRIMARY"
    READ_REPLICA = "READ_REPLICA"
    FAILOVER_REPLICA = "FAILOVER_REPLICA"
    REGIONAL_REPLICA = "REGIONAL_REPLICA"
    REPORTING_REPLICA = "REPORTING_REPLICA"
    STANDALONE_SERVICE = "STANDALONE_SERVICE"
    UNKNOWN = "UNKNOWN"


class SubjectIdentityProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str
    primary_email: str
    all_emails: Set[str]
    email_hashes: Set[str]
    phones: Set[str]
    resolved_via: str  # e.g., "user_identities.csv + user_audit_log.csv"
    audit_at: str


class ResourceAssociation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resource_id: str
    system_id: str
    associated_subject: str
    association_method: AssociationMethod
    raw_source_file: str
    physical_copy_scope: PhysicalCopyScope


class ObservedResourceState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resource_id: str
    system_id: str
    observed_state: StateSignal
    evidence_id: str
    captured_at: str
    is_authoritative: bool
    physical_copy_scope: PhysicalCopyScope
    raw_excerpt: str


class PolicyTreatmentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resource_id: str
    system_id: str
    observed_state: StateSignal
    required_policy_action: str
    proposed_remediation_op: Optional[str] = None
    proposed_remediation_state: Optional[str] = None
    target_verification_op: str
    target_verification_state: str
    finding_evidence_id: Optional[str] = None
    verification_evidence_id: Optional[str] = None
