"""Unit tests for the domain schemas: validation, bounds, round-trips, and helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from aql.domain.incidents import (
    IncidentCategory,
    IncidentClassification,
    IncidentInput,
    Severity,
    severity_distance,
)
from aql.domain.remediation import EvidenceRef, RemediationPlan, RemediationStep, RiskLevel
from aql.domain.tools_schema import (
    OpenTicketArgs,
    SearchLogsArgs,
    ToolCall,
    ToolName,
    ToolResult,
    ToolStatus,
    validate_args,
)

_NOW = datetime(2026, 6, 30, 11, 2, 0, tzinfo=UTC)


class TestIncidents:
    def test_incident_input_is_frozen_and_strict(self) -> None:
        inc = IncidentInput(
            id="INC-1",
            title="t",
            description="d",
            service="checkout",
            signal="alert",
            received_at=_NOW,
        )
        with pytest.raises(ValidationError):
            inc.service = "other"  # type: ignore[misc]  # frozen
        with pytest.raises(ValidationError):
            IncidentInput(  # type: ignore[call-arg]
                id="INC-1",
                title="t",
                description="d",
                service="s",
                signal="a",
                received_at=_NOW,
                extra_field="boom",
            )

    @pytest.mark.parametrize("confidence", [-0.1, 1.1])
    def test_classification_confidence_bounds(self, confidence: float) -> None:
        with pytest.raises(ValidationError):
            IncidentClassification(
                severity=Severity.SEV2,
                category=IncidentCategory.LATENCY,
                summary="s",
                confidence=confidence,
                rationale="r",
            )

    def test_severity_rank_and_distance(self) -> None:
        assert Severity.SEV1.rank == 1
        assert Severity.SEV4.rank == 4
        assert severity_distance(Severity.SEV1, Severity.SEV3) == 2
        assert severity_distance(Severity.SEV2, Severity.SEV2) == 0


class TestToolSchemas:
    def test_search_logs_defaults_and_bounds(self) -> None:
        args = SearchLogsArgs(service="checkout", query="ERROR")
        assert args.since == "15m" and args.limit == 100
        with pytest.raises(ValidationError):
            SearchLogsArgs(service="checkout", query="ERROR", limit=0)
        with pytest.raises(ValidationError):
            SearchLogsArgs(service="checkout", query="ERROR", since="yesterday")

    def test_open_ticket_requires_severity_enum(self) -> None:
        ok = OpenTicketArgs(title="t", service="checkout", severity=Severity.SEV2, body="b")
        assert ok.escalate is False
        with pytest.raises(ValidationError):
            OpenTicketArgs(title="t", service="checkout", severity="urgent", body="b")

    def test_validate_args_dispatches_per_tool(self) -> None:
        model = validate_args(ToolName.READ_RUNBOOK, {"slug": "checkout-latency"})
        assert model.model_dump()["slug"] == "checkout-latency"
        with pytest.raises(ValidationError):
            validate_args(ToolName.READ_RUNBOOK, {"slug": "Invalid Slug!"})

    def test_tool_call_and_result_round_trip(self) -> None:
        call = ToolCall(
            id="tc-1", name=ToolName.SEARCH_LOGS, arguments={"query": "ERROR"}, requested_at=_NOW
        )
        result = ToolResult(
            call_id=call.id,
            name=call.name,
            status=ToolStatus.OK,
            result={"total_matched": 3},
            latency_ms=12.5,
        )
        assert ToolResult.model_validate_json(result.model_dump_json()) == result


class TestRemediation:
    def _plan(self, **overrides: object) -> RemediationPlan:
        base: dict[str, object] = {
            "incident_summary": "Checkout latency",
            "root_cause_hypothesis": "pool exhaustion",
            "risk_level": RiskLevel.MEDIUM,
            "steps": [RemediationStep(order=1, action="Raise DB pool", requires_approval=True)],
            "rollback": "Revert pool size.",
            "references": [
                EvidenceRef(kind="runbook", ref="checkout-latency", tool_call_id="tc-1")
            ],
            "requires_human_approval": True,
        }
        base.update(overrides)
        return RemediationPlan(**base)

    def test_plan_requires_steps_and_references(self) -> None:
        assert self._plan().risk_level is RiskLevel.MEDIUM
        with pytest.raises(ValidationError):
            self._plan(steps=[])
        with pytest.raises(ValidationError):
            self._plan(references=[])
