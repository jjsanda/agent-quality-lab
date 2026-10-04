"""Tool contracts: the strict schemas for every tool the agent may call.

There are exactly four tools, and the surface is **read-only telemetry plus ``open_ticket``** —
there is no ``restart``, ``delete``, ``scale``, or shell tool anywhere, by design. Each tool has
a strict ``*Args`` model (``extra="forbid"``, bounded fields) and a ``*Result`` model. The
:data:`ARGS_FOR` / :data:`RESULT_FOR` maps are the single source of truth that the tool registry
(for Anthropic tool definitions), the executor (for argument validation), and the safety policy
all build on, so a schema change propagates everywhere at once.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aql.domain.incidents import Severity

__all__ = [
    "ToolName",
    "ToolStatus",
    "SearchLogsArgs",
    "LogLine",
    "SearchLogsResult",
    "QueryMetricsArgs",
    "MetricPoint",
    "QueryMetricsResult",
    "ReadRunbookArgs",
    "RunbookResult",
    "OpenTicketArgs",
    "OpenTicketResult",
    "ProposedToolCall",
    "ToolCall",
    "ToolResult",
    "ARGS_FOR",
    "RESULT_FOR",
    "validate_args",
]

# A relative window ("15m", "2h", "7d") or an ISO-8601 instant.
_SINCE_PATTERN = (
    r"^(\d{1,4}[smhd]|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)$"
)
_SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{0,126}[a-z0-9]$"


class ToolName(StrEnum):
    """The closed set of tools the agent is allowed to call."""

    SEARCH_LOGS = "search_logs"
    QUERY_METRICS = "query_metrics"
    READ_RUNBOOK = "read_runbook"
    OPEN_TICKET = "open_ticket"


class ToolStatus(StrEnum):
    """Outcome of a single tool execution."""

    OK = "ok"
    ERROR = "error"
    REFUSED = "refused"
    TIMEOUT = "timeout"


# --- search_logs -----------------------------------------------------------------------


class SearchLogsArgs(BaseModel):
    """Arguments for ``search_logs``."""

    model_config = ConfigDict(extra="forbid")

    service: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=1, max_length=512)
    since: str = Field(default="15m", pattern=_SINCE_PATTERN)
    limit: int = Field(default=100, ge=1, le=1000)


class LogLine(BaseModel):
    """A single structured log line."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    level: str = Field(max_length=16)
    service: str = Field(max_length=128)
    message: str = Field(max_length=2000)
    trace_id: str | None = Field(default=None, max_length=64)


class SearchLogsResult(BaseModel):
    """Result of ``search_logs``."""

    model_config = ConfigDict(extra="forbid")

    lines: list[LogLine] = Field(default_factory=list)
    total_matched: int = Field(ge=0)
    truncated: bool = False


# --- query_metrics ---------------------------------------------------------------------


class QueryMetricsArgs(BaseModel):
    """Arguments for ``query_metrics``."""

    model_config = ConfigDict(extra="forbid")

    service: str = Field(min_length=1, max_length=128)
    metric: str = Field(min_length=1, max_length=128)
    aggregation: Literal["avg", "p50", "p95", "p99", "max", "rate"]
    since: str = Field(default="1h", pattern=_SINCE_PATTERN)
    step: str = Field(default="1m", pattern=r"^\d{1,4}[smhd]$")


class MetricPoint(BaseModel):
    """A single (timestamp, value) sample."""

    model_config = ConfigDict(extra="forbid")

    t: datetime
    v: float


class QueryMetricsResult(BaseModel):
    """Result of ``query_metrics``."""

    model_config = ConfigDict(extra="forbid")

    metric: str = Field(max_length=128)
    unit: str = Field(max_length=32)
    aggregation: str = Field(max_length=16)
    series: list[MetricPoint] = Field(default_factory=list)


# --- read_runbook ----------------------------------------------------------------------


class ReadRunbookArgs(BaseModel):
    """Arguments for ``read_runbook``."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=128, pattern=_SLUG_PATTERN)
    section: str | None = Field(default=None, max_length=128)


class RunbookResult(BaseModel):
    """Result of ``read_runbook`` — note ``content`` is **untrusted** text (see the policy)."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(max_length=128)
    title: str = Field(max_length=200)
    content: str = Field(max_length=20_000)
    version: str = Field(max_length=32)


# --- open_ticket -----------------------------------------------------------------------


class OpenTicketArgs(BaseModel):
    """Arguments for ``open_ticket`` (the only non-read tool; still side-effect-light)."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    service: str = Field(min_length=1, max_length=128)
    severity: Severity
    body: str = Field(min_length=1, max_length=4000)
    escalate: bool = False


class OpenTicketResult(BaseModel):
    """Result of ``open_ticket``."""

    model_config = ConfigDict(extra="forbid")

    ticket_id: str = Field(max_length=64)
    url: str = Field(max_length=512)
    status: Literal["open", "escalated"]


# --- envelopes -------------------------------------------------------------------------


class ProposedToolCall(BaseModel):
    """A tool call the planner *wants* to make (validated, then stamped into a ``ToolCall``)."""

    model_config = ConfigDict(extra="forbid")

    name: ToolName
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = Field(default=None, max_length=400)


class ToolCall(BaseModel):
    """A stamped, ready-to-execute tool call (id + timestamp from the injected Clock/IdGen)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    name: ToolName
    arguments: dict[str, Any] = Field(default_factory=dict)
    requested_at: datetime


class ToolResult(BaseModel):
    """The outcome of executing a :class:`ToolCall`."""

    model_config = ConfigDict(extra="forbid")

    call_id: str = Field(min_length=1, max_length=64)
    name: ToolName
    status: ToolStatus
    result: dict[str, Any] | None = None
    error: str | None = Field(default=None, max_length=1000)
    latency_ms: float = Field(ge=0.0)


# --- registry of arg/result models -----------------------------------------------------

ARGS_FOR: dict[ToolName, type[BaseModel]] = {
    ToolName.SEARCH_LOGS: SearchLogsArgs,
    ToolName.QUERY_METRICS: QueryMetricsArgs,
    ToolName.READ_RUNBOOK: ReadRunbookArgs,
    ToolName.OPEN_TICKET: OpenTicketArgs,
}

RESULT_FOR: dict[ToolName, type[BaseModel]] = {
    ToolName.SEARCH_LOGS: SearchLogsResult,
    ToolName.QUERY_METRICS: QueryMetricsResult,
    ToolName.READ_RUNBOOK: RunbookResult,
    ToolName.OPEN_TICKET: OpenTicketResult,
}


def validate_args(name: ToolName, arguments: dict[str, Any]) -> BaseModel:
    """Validate ``arguments`` against the arg model for ``name`` (raises ``ValidationError``).

    Example:
        >>> validate_args(ToolName.READ_RUNBOOK, {"slug": "checkout-latency"})
        ReadRunbookArgs(slug='checkout-latency', section=None)
    """
    return ARGS_FOR[name].model_validate(arguments)
