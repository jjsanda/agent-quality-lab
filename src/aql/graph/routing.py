"""Conditional-edge routers — pure functions of the state that name the next node."""

from __future__ import annotations

from aql.domain.state import AgentState

__all__ = ["route_after_plan", "route_after_validate", "route_after_validate_plan"]


def route_after_plan(state: AgentState) -> str:
    """After planning: refuse if flagged, gather evidence if there are calls, else synthesize."""
    if state.refusal is not None:
        return "refuse"
    if state.planned_calls:
        return "act"
    return "synthesize"


def route_after_validate(state: AgentState) -> str:
    """After validating a tool result: run the next call (bounded) or move to synthesis."""
    limit = min(len(state.planned_calls), state.budget.max_tool_steps)
    return "act" if state.cursor < limit else "synthesize"


def route_after_validate_plan(state: AgentState) -> str:
    """After vetting the plan: refuse, finish, or loop back to synthesize (retry-with-feedback)."""
    if state.refusal is not None:
        return "refuse"
    if state.remediation is not None:
        return "finalize"
    return "synthesize"
