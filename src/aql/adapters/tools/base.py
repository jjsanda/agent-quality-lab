"""The telemetry transport port — the seam every tool call passes through.

The graph and the executor depend only on this Protocol; concrete implementations are the
in-process :class:`~aql.adapters.tools.telemetry_fake.FakeTelemetryClient` (offline/eval) and the
network :class:`~aql.adapters.tools.telemetry_http.HttpTelemetryClient` (the Go service). They are
interchangeable behind this interface — adding another transport (e.g. gRPC) is one more adapter,
with no change to the agent.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from aql.domain.tools_schema import (
    OpenTicketArgs,
    OpenTicketResult,
    QueryMetricsArgs,
    QueryMetricsResult,
    ReadRunbookArgs,
    RunbookResult,
    SearchLogsArgs,
    SearchLogsResult,
)

__all__ = ["TelemetryClient"]


@runtime_checkable
class TelemetryClient(Protocol):
    """Read-only telemetry/runbook access plus ticket creation. No mutating operations exist."""

    async def search_logs(self, args: SearchLogsArgs) -> SearchLogsResult:
        """Return matching log lines for a service."""

    async def query_metrics(self, args: QueryMetricsArgs) -> QueryMetricsResult:
        """Return an aggregated metric time series for a service."""

    async def read_runbook(self, args: ReadRunbookArgs) -> RunbookResult:
        """Return a runbook by slug (its content is *untrusted* data)."""

    async def open_ticket(self, args: OpenTicketArgs) -> OpenTicketResult:
        """File (or escalate) an incident ticket."""

    async def healthy(self) -> bool:
        """Return ``True`` if the backend is reachable."""

    async def aclose(self) -> None:
        """Release any held resources (network clients). No-op for in-process adapters."""
