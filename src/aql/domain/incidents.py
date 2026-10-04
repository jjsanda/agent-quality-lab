"""Incident inputs and the agent's incident *classification* output.

These are the first and one of the last things the agent touches: an :class:`IncidentInput`
comes in, and the ``plan`` node produces an :class:`IncidentClassification`. Both are strict
(``extra="forbid"``) so a malformed or prompt-injected payload is rejected at the boundary.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "Severity",
    "IncidentCategory",
    "IncidentInput",
    "IncidentClassification",
    "severity_distance",
]


class Severity(StrEnum):
    """Incident severity, most-severe first (``sev1`` is a full outage)."""

    SEV1 = "sev1"
    SEV2 = "sev2"
    SEV3 = "sev3"
    SEV4 = "sev4"

    @property
    def rank(self) -> int:
        """Numeric rank where 1 is the most severe.

        Example:
            >>> Severity.SEV1.rank, Severity.SEV4.rank
            (1, 4)
        """
        return int(self.value.removeprefix("sev"))


class IncidentCategory(StrEnum):
    """The failure mode the incident represents (drives which tools the agent reaches for)."""

    LATENCY = "latency"
    ERROR_RATE = "error_rate"
    SATURATION = "saturation"
    CRASH_LOOP = "crash_loop"
    DEPLOY_REGRESSION = "deploy_regression"
    DEPENDENCY_OUTAGE = "dependency_outage"
    DATA = "data"
    UNKNOWN = "unknown"


class IncidentInput(BaseModel):
    """An incident handed to the agent for triage (frozen: inputs are never mutated)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    service: str = Field(min_length=1, max_length=128)
    signal: str = Field(min_length=1, max_length=400, description="The alert/symptom that fired.")
    received_at: datetime


class IncidentClassification(BaseModel):
    """The agent's structured triage of an incident (the ``plan`` node's first output)."""

    model_config = ConfigDict(extra="forbid")

    severity: Severity
    category: IncidentCategory
    summary: str = Field(min_length=1, max_length=280)
    affected_services: list[str] = Field(default_factory=list, max_length=20)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1, max_length=1000)


def severity_distance(a: Severity, b: Severity) -> int:
    """Absolute distance between two severities on the sev1..sev4 scale.

    Used by the ``severity_within_1`` evaluation metric to score "close enough" triage.

    Example:
        >>> severity_distance(Severity.SEV1, Severity.SEV2)
        1
        >>> severity_distance(Severity.SEV2, Severity.SEV2)
        0
    """
    return abs(a.rank - b.rank)
