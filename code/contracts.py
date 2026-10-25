"""
Data contracts for HackerRank Orchestrate (October 2026) - Ghost Data Still Exists.
Built with Pydantic v2, extra="forbid", and strict type definitions.
"""

from __future__ import annotations
from enum import Enum
from datetime import datetime
from typing import Literal, List, Optional, Union, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DeletionStatus(str, Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Phase(str, Enum):
    FINDING = "FINDING"
    REMEDIATION = "REMEDIATION"
    VERIFICATION = "VERIFICATION"


class FindingOperation(str, Enum):
    REPORT_REMAINING_RECORD = "REPORT_REMAINING_RECORD"
    REPORT_EXPOSED_PII = "REPORT_EXPOSED_PII"
    REPORT_ACTIVE_DATA_FLOW = "REPORT_ACTIVE_DATA_FLOW"
    REPORT_RESTORE_RISK = "REPORT_RESTORE_RISK"


class RemediationOperation(str, Enum):
    DISABLE_DATA_FLOW = "DISABLE_DATA_FLOW"
    BLOCK_RESTORE = "BLOCK_RESTORE"
    DELETE_RECORD = "DELETE_RECORD"
    REDACT_RECORD = "REDACT_RECORD"
    ANONYMIZE_RECORD = "ANONYMIZE_RECORD"


class VerificationOperation(str, Enum):
    VERIFY_RECORD_ABSENT = "VERIFY_RECORD_ABSENT"
    VERIFY_RECORD_PRESENT = "VERIFY_RECORD_PRESENT"
    VERIFY_RECORD_REDACTED = "VERIFY_RECORD_REDACTED"
    VERIFY_RECORD_ANONYMIZED = "VERIFY_RECORD_ANONYMIZED"
    VERIFY_DATA_FLOW_DISABLED = "VERIFY_DATA_FLOW_DISABLED"
    VERIFY_RESTORE_BLOCKED = "VERIFY_RESTORE_BLOCKED"


AllOperation = Union[FindingOperation, RemediationOperation, VerificationOperation]


class ResourceStateEnum(str, Enum):
    PRESENT = "PRESENT"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"
    ABSENT = "ABSENT"
    REDACTED = "REDACTED"
    ANONYMIZED = "ANONYMIZED"


class ContractBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Request(ContractBaseModel):
    case_id: str
    email: str
    requested_at: datetime
    reported_status: str
    reported_at: datetime
    audit_at: datetime
    request_text: str


class EvidenceItem(ContractBaseModel):
    file_id: str
    file_path: str
    origin: str
    captured_at: datetime


class ResourceState(ContractBaseModel):
    system_id: str
    resource_id: str
    state: ResourceStateEnum
    evidence_id: str
    observed_at: datetime


class Finding(ContractBaseModel):
    step_no: int = Field(ge=1)
    phase: Literal[Phase.FINDING] = Phase.FINDING
    system_id: str
    resource_id: str
    operation: FindingOperation
    state: ResourceStateEnum
    evidence_id: str = Field(min_length=1)


class Remediation(ContractBaseModel):
    step_no: int = Field(ge=1)
    phase: Literal[Phase.REMEDIATION] = Phase.REMEDIATION
    system_id: str
    resource_id: str
    operation: RemediationOperation
    state: ResourceStateEnum
    evidence_id: Literal[""] = ""


class Verification(ContractBaseModel):
    step_no: int = Field(ge=1)
    phase: Literal[Phase.VERIFICATION] = Phase.VERIFICATION
    system_id: str
    resource_id: str
    operation: VerificationOperation
    state: ResourceStateEnum
    evidence_id: str = ""


StepItem = Union[Finding, Remediation, Verification]


class Step(ContractBaseModel):
    """Generic Step model matching output JSON schema."""
    model_config = ConfigDict(extra="forbid", strict=False)

    step_no: int = Field(ge=1)
    phase: Phase
    system_id: str
    resource_id: str
    operation: str
    state: ResourceStateEnum
    evidence_id: str = ""

    @model_validator(mode="after")
    def validate_step_consistency(self) -> Step:
        # Validate operation matches phase
        if self.phase == Phase.FINDING:
            if self.operation not in [op.value for op in FindingOperation]:
                raise ValueError(f"Invalid operation '{self.operation}' for phase FINDING")
            if not self.evidence_id:
                raise ValueError("FINDING step must have non-empty evidence_id")
        elif self.phase == Phase.REMEDIATION:
            if self.operation not in [op.value for op in RemediationOperation]:
                raise ValueError(f"Invalid operation '{self.operation}' for phase REMEDIATION")
            if self.evidence_id != "":
                raise ValueError("REMEDIATION step must have empty evidence_id")
        elif self.phase == Phase.VERIFICATION:
            if self.operation not in [op.value for op in VerificationOperation]:
                raise ValueError(f"Invalid operation '{self.operation}' for phase VERIFICATION")
        return self


class OutputRow(ContractBaseModel):
    case_id: str
    deletion_status: DeletionStatus
    steps: List[Step] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_output_row(self) -> OutputRow:
        if self.deletion_status == DeletionStatus.NOT_APPLICABLE:
            if len(self.steps) != 0:
                raise ValueError("NOT_APPLICABLE status must have empty steps list")
        elif self.deletion_status == DeletionStatus.COMPLETE:
            for s in self.steps:
                if s.phase != Phase.VERIFICATION:
                    raise ValueError(f"COMPLETE status must only have VERIFICATION steps, found {s.phase}")
                if not s.evidence_id:
                    raise ValueError("COMPLETE verification steps must have evidence_id")
        elif self.deletion_status == DeletionStatus.INCOMPLETE:
            # Must have finding, remediation, verification steps
            phases_present = {s.phase for s in self.steps}
            if Phase.FINDING not in phases_present:
                raise ValueError("INCOMPLETE status must contain FINDING steps")
        return self


class VerdictCertainty(str, Enum):
    CONFIRMED = "CONFIRMED"
    BLOCKED_EMPTY_DISCOVERY = "BLOCKED_EMPTY_DISCOVERY"
    BLOCKED_ASSOCIATION_GAP = "BLOCKED_ASSOCIATION_GAP"
    BLOCKED_UNRESOLVED_SCOPE = "BLOCKED_UNRESOLVED_SCOPE"
    BLOCKED_UNRESOLVED_CONFLICT = "BLOCKED_UNRESOLVED_CONFLICT"
    BLOCKED_UNKNOWN_POLICY_CONDITION = "BLOCKED_UNKNOWN_POLICY_CONDITION"


class PlanCompleteness(str, Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE_SCOPE = "INCOMPLETE_SCOPE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CaseEvaluationResult(ContractBaseModel):
    case_id: str
    is_deletion: bool
    status: Optional[DeletionStatus] = None
    verdict_certainty: VerdictCertainty
    plan_completeness: PlanCompleteness
    steps: List[Step] = Field(default_factory=list)
    diagnostics: List[str] = Field(default_factory=list)
    provenance: Dict[str, Any] = Field(default_factory=dict)

    def is_blocked(self) -> bool:
        return self.verdict_certainty != VerdictCertainty.CONFIRMED or self.status is None

    def __iter__(self):
        st_val = self.status.value if self.status else ""
        st_steps = [s.model_dump() if hasattr(s, "model_dump") else s for s in self.steps]
        return iter((st_val, st_steps))

    def __getitem__(self, idx):
        return tuple(self)[idx]
