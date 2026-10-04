"""The LLM port: a two-stage, structured interface the graph depends on.

Instead of exposing a raw "messages" loop, the engine offers exactly the two structured calls
the agent makes — :meth:`plan` (classify + choose tool calls) and :meth:`synthesize` (produce a
remediation plan). Both return validated Pydantic models plus token usage. The graph is
identical whether the engine behind this port is the deterministic rule engine or real Claude.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from aql.domain.incidents import IncidentClassification, IncidentInput
from aql.domain.remediation import RemediationPlan
from aql.domain.state import TokenUsage
from aql.domain.tools_schema import ProposedToolCall, ToolResult

__all__ = ["PlanOutput", "PlanResult", "SynthResult", "LLMEngine"]


class PlanOutput(BaseModel):
    """The structured output of the PLAN stage: a classification + the tool calls to run."""

    model_config = ConfigDict(extra="forbid")

    classification: IncidentClassification
    tool_calls: list[ProposedToolCall] = Field(default_factory=list, max_length=8)


class PlanResult(BaseModel):
    """``plan()`` return: the plan output plus the token usage that produced it."""

    model_config = ConfigDict(extra="forbid")

    output: PlanOutput
    usage: TokenUsage


class SynthResult(BaseModel):
    """``synthesize()`` return: the remediation plan plus token usage."""

    model_config = ConfigDict(extra="forbid")

    plan: RemediationPlan
    usage: TokenUsage


class LLMEngine(Protocol):
    """The structured-LLM port. Async so it composes with the async tool layer."""

    @property
    def provider(self) -> str:
        """Short provider id for traces, e.g. ``"deterministic"`` or ``"anthropic"``."""

    @property
    def model(self) -> str:
        """Model id for traces and cost accounting."""

    async def plan(self, incident: IncidentInput, *, feedback: str | None = None) -> PlanResult:
        """Classify the incident and choose the read-only tool calls to gather evidence."""

    async def synthesize(
        self,
        incident: IncidentInput,
        classification: IncidentClassification,
        tool_results: list[ToolResult],
        *,
        feedback: str | None = None,
    ) -> SynthResult:
        """Produce an advisory remediation plan grounded in the gathered evidence."""

    async def aclose(self) -> None:
        """Release any provider network resources (no-op for in-process engines)."""
