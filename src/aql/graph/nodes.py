"""The graph nodes — the agent's behaviour, one responsibility per node.

Flow: ``plan`` classifies and chooses read-only tool calls (refusing up-front if the incident
input is prompt-injected); ``act``/``validate`` run each call and scan its output for injected
content (recorded, never acted on); ``synthesize``/``validate_plan`` produce and vet the
remediation plan. ``validate_plan`` splits policy failures into *recoverable* ones
(missing-rollback / unapproved-destructive → bounded retry with feedback) and *hard* ones
(injected / catastrophic-command → refuse). ``refuse`` takes the safe action — escalate a ticket.
"""

from __future__ import annotations

from typing import Any

from aql.adapters.llm.base import LLMEngine
from aql.adapters.tools.executor import ToolExecutor
from aql.domain.evidence import evidence_ref_from_result
from aql.domain.incidents import Severity
from aql.domain.policy import (
    SafetyCategory,
    classify_remediation_safety,
    classify_tool_call_safety,
    extract_text,
    find_injection_markers,
)
from aql.domain.state import AgentState, RefusalDecision, TokenUsage, ValidationIssue
from aql.domain.tools_schema import ProposedToolCall, ToolCall, ToolName, ToolStatus
from aql.graph.tracing import child_span

__all__ = ["Nodes"]

_HARD_REFUSE = {SafetyCategory.INJECTED_DIRECTIVE, SafetyCategory.DESTRUCTIVE_COMMAND}


def _record_usage(span: Any, usage: TokenUsage) -> None:
    if span is not None:
        span.set_attribute("gen_ai.usage.input_tokens", usage.input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", usage.output_tokens)


class Nodes:
    """Bundles the node implementations over an :class:`LLMEngine` + :class:`ToolExecutor`."""

    def __init__(self, engine: LLMEngine, executor: ToolExecutor) -> None:
        self._engine = engine
        self._executor = executor

    async def plan(self, state: AgentState) -> dict[str, Any]:
        with child_span(
            "aql.llm.plan",
            **{"gen_ai.system": self._engine.provider, "gen_ai.request.model": self._engine.model},
        ) as span:
            result = await self._engine.plan(state.incident)
            _record_usage(span, result.usage)
        classification = result.output.classification
        updates: dict[str, Any] = {"classification": classification, "usages": [result.usage]}

        incident_text = "\n".join(
            (state.incident.title, state.incident.signal, state.incident.description)
        )
        markers = find_injection_markers(incident_text)
        if markers:
            updates["refusal"] = RefusalDecision(
                reason=f"incident input contains injected directive(s): {', '.join(markers)}",
                category=SafetyCategory.INJECTED_DIRECTIVE.value,
            )
            updates["log_events"] = ["plan: refusing — injected directive in incident input"]
            return updates

        planned: list[ToolCall] = []
        for proposed in result.output.tool_calls:
            verdict = classify_tool_call_safety(proposed)
            if verdict.decision == "refuse":
                updates["refusal"] = RefusalDecision(
                    reason=verdict.reason, category=verdict.category.value
                )
                updates["log_events"] = [
                    f"plan: refusing — unsafe tool call ({verdict.category.value})"
                ]
                return updates
            planned.append(self._executor.stamp(proposed))

        updates["planned_calls"] = planned
        updates["cursor"] = 0
        updates["log_events"] = [
            f"plan: {classification.severity.value}/{classification.category.value}, "
            f"{len(planned)} tool call(s)"
        ]
        return updates

    async def act(self, state: AgentState) -> dict[str, Any]:
        call = state.planned_calls[state.cursor]
        with child_span(f"aql.tool.{call.name.value}", **{"tool.name": call.name.value}) as span:
            result = await self._executor.execute(call)
            if span is not None:
                span.set_attribute("tool.status", result.status.value)
                span.set_attribute("tool.latency_ms", result.latency_ms)
        updates: dict[str, Any] = {
            "tool_results": [result],
            "cursor": state.cursor + 1,
            "log_events": [f"act: {call.name.value} -> {result.status.value}"],
        }
        ref = evidence_ref_from_result(result)
        if ref is not None:
            updates["evidence"] = [ref]
        return updates

    async def validate(self, state: AgentState) -> dict[str, Any]:
        last = state.tool_results[-1]
        events: list[str] = []
        markers = find_injection_markers(extract_text(last.result or {}))
        if markers:
            events.append(
                f"validate: injected content in {last.name.value} output detected and ignored "
                f"({', '.join(markers)})"
            )
        if last.status is not ToolStatus.OK:
            events.append(f"validate: {last.name.value} returned {last.status.value}")
        return {"log_events": events} if events else {}

    async def synthesize(self, state: AgentState) -> dict[str, Any]:
        assert state.classification is not None  # only reached after a successful plan
        feedback = (
            "; ".join(f"{issue.code}: {issue.detail}" for issue in state.validation_errors)
            if state.validation_errors
            else None
        )
        with child_span(
            "aql.llm.synthesize",
            **{"gen_ai.system": self._engine.provider, "gen_ai.request.model": self._engine.model},
        ) as span:
            result = await self._engine.synthesize(
                state.incident, state.classification, state.tool_results, feedback=feedback
            )
            _record_usage(span, result.usage)
        note = f"synthesize: draft plan, {len(result.plan.steps)} step(s)"
        if feedback:
            note += " (retry)"
        return {"draft_plan": result.plan, "usages": [result.usage], "log_events": [note]}

    async def validate_plan(self, state: AgentState) -> dict[str, Any]:
        assert state.draft_plan is not None
        verdict = classify_remediation_safety(state.draft_plan)
        if verdict.decision == "allow":
            return {"remediation": state.draft_plan, "log_events": ["validate_plan: accepted"]}

        recoverable = verdict.category not in _HARD_REFUSE
        if recoverable and state.retry_count < state.budget.max_retries:
            issue = ValidationIssue(code=verdict.category.value, detail=verdict.reason)
            return {
                "validation_errors": [issue],
                "retry_count": state.retry_count + 1,
                "draft_plan": None,
                "log_events": [f"validate_plan: retry ({verdict.category.value})"],
            }

        return {
            "refusal": RefusalDecision(reason=verdict.reason, category=verdict.category.value),
            "draft_plan": None,
            "log_events": [f"validate_plan: refusing ({verdict.category.value})"],
        }

    async def refuse(self, state: AgentState) -> dict[str, Any]:
        reason = state.refusal.reason if state.refusal else "unsafe condition detected"
        category = state.refusal.category if state.refusal else SafetyCategory.SAFE.value
        severity = state.classification.severity if state.classification else Severity.SEV2
        proposed = ProposedToolCall(
            name=ToolName.OPEN_TICKET,
            arguments={
                "title": f"[escalation] {state.incident.title}"[:200],
                "service": state.incident.service,
                "severity": severity.value,
                "body": f"The agent refused to proceed and escalated to a human.\nReason: {reason}"[
                    :4000
                ],
                "escalate": True,
            },
        )
        with child_span(
            "aql.tool.open_ticket", **{"tool.name": "open_ticket", "aql.escalation": True}
        ) as span:
            result = await self._executor.execute(self._executor.stamp(proposed))
            if span is not None:
                span.set_attribute("tool.status", result.status.value)
        ticket_id = result.result.get("ticket_id") if result.result else None
        return {
            "refusal": RefusalDecision(
                reason=reason, category=category, escalated_ticket_id=ticket_id
            ),
            "tool_results": [result],
            "log_events": [f"refuse: escalated via ticket {ticket_id}"],
        }

    async def finalize(self, state: AgentState) -> dict[str, Any]:
        return {"log_events": ["finalize: diagnosis complete"]}
