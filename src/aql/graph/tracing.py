"""Wrap a graph node so each execution becomes an OpenTelemetry span (when tracing is on).

A plain pass-through when no tracer is configured, so the graph is identical offline.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from typing import Any

from aql.domain.state import AgentState
from aql.observability.tracing import get_tracer

__all__ = ["NodeFn", "traced", "child_span"]

NodeFn = Callable[[AgentState], Awaitable[dict[str, Any]]]


@contextmanager
def child_span(name: str, **attributes: Any) -> Iterator[Any]:
    """Open a child span with attributes (yields the span, or ``None`` when tracing is off)."""
    tracer = get_tracer()
    if tracer is None:
        yield None
        return
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            span.set_attribute(key, value)
        yield span


def traced(name: str, fn: NodeFn) -> NodeFn:
    """Return ``fn`` wrapped to emit an ``aql.node.<name>`` span per call."""

    async def wrapper(state: AgentState) -> dict[str, Any]:
        tracer = get_tracer()
        if tracer is None:
            return await fn(state)
        with tracer.start_as_current_span(f"aql.node.{name}") as span:
            updates = await fn(state)
            span.set_attribute("aql.node", name)
            span.set_attribute("aql.retry_count", state.retry_count)
            return updates

    return wrapper
