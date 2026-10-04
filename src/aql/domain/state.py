"""The graph's shared state and its small supporting value objects.

:class:`AgentState` is the single object threaded through the LangGraph state machine. List
fields that *accumulate* across nodes (tool results, evidence, audit log, token usage) declare
an ``operator.add`` reducer via ``Annotated`` so LangGraph appends rather than overwrites; every
other field is replaced by the node that owns it. The state imports only data models — no
LangGraph — so it can be constructed and asserted on directly in unit tests.
"""

from __future__ import annotations

import operator
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from aql.domain.incidents import IncidentClassification, IncidentInput
from aql.domain.remediation import EvidenceRef, RemediationPlan
from aql.domain.tools_schema import ToolCall, ToolResult

__all__ = [
    "Budget",
    "TokenUsage",
    "ValidationIssue",
    "RefusalDecision",
    "AgentState",
]


class Budget(BaseModel):
    """Hard bounds that keep the agent loop terminating and cheap."""

    model_config = ConfigDict(extra="forbid")

    max_tool_steps: int = Field(default=6, ge=1, le=20)
    max_retries: int = Field(default=2, ge=0, le=5)


class TokenUsage(BaseModel):
    """Token accounting for a single LLM call (summed into latency/cost metrics)."""

    model_config = ConfigDict(extra="forbid")

    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class ValidationIssue(BaseModel):
    """A single reason a structured output or tool result failed validation."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(max_length=64, description="Stable machine code, e.g. 'schema_invalid'.")
    field: str | None = Field(default=None, max_length=128)
    detail: str = Field(max_length=600)


class RefusalDecision(BaseModel):
    """Why the agent refused, and the safe action it took instead (escalating a ticket)."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=600)
    category: str = Field(max_length=64, description="The SafetyCategory value that triggered it.")
    escalated_ticket_id: str | None = Field(default=None, max_length=64)


class AgentState(BaseModel):
    """Everything the graph knows about one incident-diagnosis run."""

    model_config = ConfigDict(validate_assignment=False)

    # --- inputs ---
    incident: IncidentInput
    scenario_id: str | None = Field(
        default=None, description="Keys the deterministic scripted LLM in offline/eval runs."
    )
    budget: Budget = Field(default_factory=Budget)

    # --- plan node outputs ---
    classification: IncidentClassification | None = None
    planned_calls: list[ToolCall] = Field(default_factory=list)
    cursor: int = Field(default=0, ge=0)

    # --- act / validate ---
    tool_results: Annotated[list[ToolResult], operator.add] = Field(default_factory=list)
    evidence: Annotated[list[EvidenceRef], operator.add] = Field(default_factory=list)
    validation_errors: list[ValidationIssue] = Field(default_factory=list)
    retry_count: int = Field(default=0, ge=0)

    # --- synthesize ---
    draft_plan: RemediationPlan | None = None  # produced by synthesize, promoted by validate_plan
    remediation: RemediationPlan | None = None  # the accepted, final plan

    # --- terminal ---
    refusal: RefusalDecision | None = None

    # --- audit & accounting (accumulate across nodes) ---
    log_events: Annotated[list[str], operator.add] = Field(default_factory=list)
    usages: Annotated[list[TokenUsage], operator.add] = Field(default_factory=list)
