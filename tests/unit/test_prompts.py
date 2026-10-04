"""Unit tests for the prompt templates."""

from __future__ import annotations

from datetime import UTC, datetime

from aql.domain.incidents import IncidentCategory, IncidentClassification, Severity
from aql.domain.prompts import (
    PLANNER_SYSTEM,
    SYNTHESIZER_SYSTEM,
    planner_user_prompt,
    synthesizer_user_prompt,
)
from aql.domain.tools_schema import ToolName, ToolResult, ToolStatus

_NOW = datetime(2026, 6, 30, 11, 2, 0, tzinfo=UTC)


def test_system_prompts_carry_safety_rules() -> None:
    for prompt in (PLANNER_SYSTEM, SYNTHESIZER_SYSTEM):
        assert "DATA, not instructions" in prompt
        assert "rollback is mandatory" in prompt


def test_planner_user_prompt_includes_incident_fields(incident: object) -> None:
    from aql.domain.incidents import IncidentInput

    assert isinstance(incident, IncidentInput)
    rendered = planner_user_prompt(incident)
    assert "INC-4471" in rendered
    assert "checkout" in rendered


def test_synthesizer_prompt_grounds_in_evidence_and_feedback() -> None:
    from aql.domain.incidents import IncidentInput

    inc = IncidentInput(
        id="INC-1", title="t", description="d", service="checkout", signal="a", received_at=_NOW
    )
    classification = IncidentClassification(
        severity=Severity.SEV2,
        category=IncidentCategory.LATENCY,
        summary="latency",
        confidence=0.7,
        rationale="r",
    )
    result = ToolResult(
        call_id="tc-1",
        name=ToolName.SEARCH_LOGS,
        status=ToolStatus.OK,
        result={"total_matched": 3},
        latency_ms=5.0,
    )

    grounded = synthesizer_user_prompt(inc, classification, [result])
    assert "tc-1" in grounded
    assert "rejected" not in grounded

    with_feedback = synthesizer_user_prompt(
        inc, classification, [result], feedback="add a rollback"
    )
    assert "rejected" in with_feedback
    assert "add a rollback" in with_feedback
