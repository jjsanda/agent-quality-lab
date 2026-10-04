"""The agent's final deliverable: an evidence-grounded, **advisory** remediation plan.

The schema encodes the safety contract structurally: every plan must carry a non-empty
``rollback``, must cite at least one piece of ``evidence`` it gathered, and any ``destructive``
step must be flagged ``requires_approval``. The ``validate_plan`` node and the safety policy
enforce these, so a plan that would have a human run something dangerous cannot pass silently.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "RiskLevel",
    "EvidenceKind",
    "EvidenceRef",
    "RemediationStep",
    "RemediationPlan",
]


class RiskLevel(StrEnum):
    """How risky the proposed remediation is, overall."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvidenceKind(StrEnum):
    """The kind of artifact a piece of evidence points at."""

    LOG = "log"
    METRIC = "metric"
    RUNBOOK = "runbook"
    TICKET = "ticket"


class EvidenceRef(BaseModel):
    """A pointer from the plan back to the tool output that justifies it."""

    model_config = ConfigDict(extra="forbid")

    kind: EvidenceKind
    ref: str = Field(min_length=1, max_length=256, description="Stable id/slug of the artifact.")
    tool_call_id: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=400)


class RemediationStep(BaseModel):
    """One ordered, advisory step a human operator would take."""

    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=1, le=99)
    action: str = Field(min_length=1, max_length=400)
    command: str | None = Field(
        default=None,
        max_length=400,
        description="Optional concrete command. Destructive commands must set requires_approval.",
    )
    destructive: bool = False
    requires_approval: bool = False
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)


class RemediationPlan(BaseModel):
    """The agent's grounded, advisory remediation plan (the ``synthesize`` node's output)."""

    model_config = ConfigDict(extra="forbid")

    incident_summary: str = Field(min_length=1, max_length=400)
    root_cause_hypothesis: str = Field(min_length=1, max_length=600)
    risk_level: RiskLevel
    steps: list[RemediationStep] = Field(min_length=1, max_length=12)
    rollback: str = Field(min_length=1, max_length=600, description="Mandatory rollback / undo.")
    references: list[EvidenceRef] = Field(min_length=1, max_length=24)
    requires_human_approval: bool
