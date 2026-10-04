"""Unit tests for the node tracing wrapper."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from aql.domain.incidents import IncidentInput
from aql.domain.state import AgentState
from aql.graph.tracing import child_span, traced

_NOW = datetime(2026, 6, 30, tzinfo=UTC)


def _state() -> AgentState:
    return AgentState(
        incident=IncidentInput(
            id="i", title="t", description="d", service="s", signal="a", received_at=_NOW
        )
    )


class _FakeSpan:
    def set_attribute(self, key: str, value: Any) -> None:
        return None


class _FakeTracer:
    @contextmanager
    def start_as_current_span(self, name: str) -> Iterator[_FakeSpan]:
        yield _FakeSpan()


async def _node(state: AgentState) -> dict[str, Any]:
    return {"cursor": 1}


async def test_traced_creates_span_when_tracer_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aql.graph.tracing.get_tracer", lambda: _FakeTracer())
    assert await traced("plan", _node)(_state()) == {"cursor": 1}


async def test_traced_is_noop_without_tracer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aql.graph.tracing.get_tracer", lambda: None)
    assert await traced("plan", _node)(_state()) == {"cursor": 1}


def test_child_span_sets_attributes(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, Any] = {}

    class _RecSpan:
        def set_attribute(self, key: str, value: Any) -> None:
            recorded[key] = value

    class _RecTracer:
        @contextmanager
        def start_as_current_span(self, name: str) -> Iterator[_RecSpan]:
            yield _RecSpan()

    monkeypatch.setattr("aql.graph.tracing.get_tracer", lambda: _RecTracer())
    with child_span("aql.tool.search_logs", **{"tool.name": "search_logs"}) as span:
        assert span is not None
        span.set_attribute("tool.status", "ok")
    assert recorded == {"tool.name": "search_logs", "tool.status": "ok"}


def test_child_span_is_noop_without_tracer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("aql.graph.tracing.get_tracer", lambda: None)
    with child_span("x", a=1) as span:
        assert span is None
