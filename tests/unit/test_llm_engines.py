"""Unit tests for the LLM engines: deterministic brain + Anthropic request shape."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from aql.adapters.llm.base import PlanOutput
from aql.adapters.llm.deterministic import DeterministicLLMEngine
from aql.domain.incidents import IncidentCategory, IncidentInput, Severity
from aql.domain.policy import classify_remediation_safety
from aql.domain.tools_schema import ToolName, ToolResult, ToolStatus, validate_args

_NOW = datetime(2026, 6, 30, 11, 2, tzinfo=UTC)


def _incident(**kw: Any) -> IncidentInput:
    base: dict[str, Any] = {
        "id": "INC-1",
        "title": "Checkout p99 latency breached SLO",
        "description": "p99 latency > 2s for 10m",
        "service": "checkout",
        "signal": "alert: checkout p99 > 2000ms",
        "received_at": _NOW,
    }
    base.update(kw)
    return IncidentInput(**base)


def _ok_results() -> list[ToolResult]:
    return [
        ToolResult(
            call_id="tc-1",
            name=ToolName.SEARCH_LOGS,
            status=ToolStatus.OK,
            result={"lines": [], "total_matched": 2},
            latency_ms=1.0,
        ),
        ToolResult(
            call_id="tc-2",
            name=ToolName.QUERY_METRICS,
            status=ToolStatus.OK,
            result={"metric": "latency_p99_ms"},
            latency_ms=1.0,
        ),
        ToolResult(
            call_id="tc-3",
            name=ToolName.READ_RUNBOOK,
            status=ToolStatus.OK,
            result={"slug": "latency-troubleshooting"},
            latency_ms=1.0,
        ),
    ]


class TestDeterministicEngine:
    async def test_classifies_latency_and_plans_read_only_tools(self) -> None:
        engine = DeterministicLLMEngine()
        result = await engine.plan(_incident())
        cls = result.output.classification
        assert cls.category is IncidentCategory.LATENCY
        assert cls.severity is Severity.SEV2  # "breached SLO" -> sev2
        assert 0.6 <= cls.confidence <= 0.9
        names = [c.name for c in result.output.tool_calls]
        assert names == [ToolName.SEARCH_LOGS, ToolName.QUERY_METRICS, ToolName.READ_RUNBOOK]
        for call in result.output.tool_calls:  # every proposed call has schema-valid arguments
            validate_args(call.name, call.arguments)
        assert result.usage.model == "deterministic-offline"

    async def test_is_byte_for_byte_deterministic(self) -> None:
        engine = DeterministicLLMEngine()
        a = await engine.plan(_incident())
        b = await engine.plan(_incident())
        assert a.output.model_dump_json() == b.output.model_dump_json()
        assert a.usage == b.usage

    async def test_unknown_incident_lowers_confidence(self) -> None:
        cls = (
            await DeterministicLLMEngine().plan(
                _incident(title="Something odd", description="weird behaviour", signal="alert: ???")
            )
        ).output.classification
        assert cls.category is IncidentCategory.UNKNOWN
        assert cls.confidence == pytest.approx(0.4)

    async def test_synthesizes_safe_grounded_plan(self) -> None:
        engine = DeterministicLLMEngine()
        cls = (await engine.plan(_incident())).output.classification
        plan = (await engine.synthesize(_incident(), cls, _ok_results())).plan
        assert plan.rollback.strip()
        assert plan.references  # grounded in gathered evidence
        assert plan.requires_human_approval is True
        assert classify_remediation_safety(plan).decision == "allow"

    async def test_synthesize_without_evidence_still_valid(self) -> None:
        engine = DeterministicLLMEngine()
        cls = (await engine.plan(_incident())).output.classification
        plan = (await engine.synthesize(_incident(), cls, [])).plan
        assert len(plan.references) >= 1  # falls back to citing the runbook


class TestAnthropicEngineShape:
    async def test_forces_tool_and_validates_output(self) -> None:
        anthropic = pytest.importorskip("anthropic")
        from aql.adapters.llm.anthropic_engine import PLAN_TOOL, AnthropicLLMEngine

        valid = PlanOutput(
            classification=(await DeterministicLLMEngine().plan(_incident())).output.classification,
            tool_calls=[],
        ).model_dump(mode="json")
        captured: dict[str, Any] = {}

        class _Messages:
            async def create(self, **kwargs: Any) -> Any:
                captured.update(kwargs)
                return SimpleNamespace(
                    content=[SimpleNamespace(type="tool_use", name=PLAN_TOOL, input=valid)],
                    usage=SimpleNamespace(input_tokens=120, output_tokens=42),
                )

        engine = AnthropicLLMEngine(
            model="claude-opus-4-8", client=SimpleNamespace(messages=_Messages())
        )
        result = await engine.plan(_incident())

        assert captured["model"] == "claude-opus-4-8"
        assert captured["tool_choice"] == {"type": "tool", "name": PLAN_TOOL}
        assert captured["tools"][0]["name"] == PLAN_TOOL
        assert captured["tools"][0]["input_schema"]["additionalProperties"] is False
        assert (result.usage.input_tokens, result.usage.output_tokens) == (120, 42)
        assert result.usage.model == "claude-opus-4-8"
        assert issubclass(anthropic.AnthropicError, Exception)
