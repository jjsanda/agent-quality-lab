"""The tool executor — the guarded boundary between the model and any transport.

The tool surface is a closed enum (:class:`~aql.domain.tools_schema.ToolName`), so only the four
known tools can ever be expressed. Every call then goes through :meth:`ToolExecutor.execute`, which:

1. **validates** the arguments against the strict Pydantic schema (rejecting injected/extra fields),
2. runs the **safety policy** (refusing injected directives / non-allowlisted tools),
3. dispatches under an :func:`asyncio.wait_for` **timeout**, and
4. **size-caps** the result.

Any failure becomes a typed ``ToolResult`` (``refused`` / ``error`` / ``timeout``) rather than an
exception, so a single bad call degrades gracefully instead of crashing the run. Timestamps and
ids come from the injected clock/id-generator, so offline runs are reproducible.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic import ValidationError

from aql.adapters.tools.base import TelemetryClient
from aql.domain.clock import Clock, IdGenerator
from aql.domain.exceptions import ToolError
from aql.domain.policy import classify_tool_call_safety
from aql.domain.tools_schema import (
    ProposedToolCall,
    ToolCall,
    ToolName,
    ToolResult,
    ToolStatus,
    validate_args,
)

__all__ = ["ToolExecutor"]

_MAX_STRING_CHARS = 8000
_MAX_LIST_ITEMS = 500


def _cap(value: Any) -> Any:
    """Recursively truncate oversized strings so a chatty tool can't blow the context budget."""
    if isinstance(value, str):
        return (
            value if len(value) <= _MAX_STRING_CHARS else value[:_MAX_STRING_CHARS] + "…(truncated)"
        )
    if isinstance(value, dict):
        return {key: _cap(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_cap(item) for item in value[:_MAX_LIST_ITEMS]]
    return value


class ToolExecutor:
    """Validates, guards, times, and dispatches tool calls against a :class:`TelemetryClient`."""

    def __init__(
        self,
        client: TelemetryClient,
        *,
        clock: Clock,
        id_gen: IdGenerator,
        timeout_s: float = 10.0,
    ) -> None:
        self._client = client
        self._clock = clock
        self._id_gen = id_gen
        self._timeout_s = timeout_s

    def stamp(self, proposed: ProposedToolCall) -> ToolCall:
        """Turn a planner's proposed call into an executable one with an id + timestamp."""
        return ToolCall(
            id=self._id_gen.new_id("tc-"),
            name=proposed.name,
            arguments=proposed.arguments,
            requested_at=self._clock.now(),
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        started = self._clock.now()

        try:
            args = validate_args(call.name, call.arguments)
        except ValidationError as exc:
            return self._result(
                call, ToolStatus.ERROR, started, error=f"invalid arguments ({exc.error_count()})"
            )

        verdict = classify_tool_call_safety(call)
        if verdict.decision == "refuse":
            return self._result(call, ToolStatus.REFUSED, started, error=verdict.reason)

        try:
            result_model = await asyncio.wait_for(
                self._dispatch(call.name, args), timeout=self._timeout_s
            )
        except TimeoutError:
            return self._result(call, ToolStatus.TIMEOUT, started, error="tool timed out")
        except (ToolError, ValidationError, json.JSONDecodeError) as exc:
            # A transport failure or a malformed/unexpected response degrades to a typed result
            # rather than aborting the whole run.
            return self._result(call, ToolStatus.ERROR, started, error=f"tool failed: {exc}")

        payload: dict[str, Any] = _cap(result_model.model_dump(mode="json"))
        return self._result(call, ToolStatus.OK, started, result=payload)

    async def _dispatch(self, name: ToolName, args: Any) -> Any:
        if name is ToolName.SEARCH_LOGS:
            return await self._client.search_logs(args)
        if name is ToolName.QUERY_METRICS:
            return await self._client.query_metrics(args)
        if name is ToolName.READ_RUNBOOK:
            return await self._client.read_runbook(args)
        return await self._client.open_ticket(args)

    def _result(
        self,
        call: ToolCall,
        status: ToolStatus,
        started: Any,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ToolResult:
        elapsed_ms = max(0.0, (self._clock.now() - started).total_seconds() * 1000.0)
        return ToolResult(
            call_id=call.id,
            name=call.name,
            status=status,
            result=result,
            error=error,
            latency_ms=elapsed_ms,
        )
