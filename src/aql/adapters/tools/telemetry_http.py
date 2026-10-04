"""HTTP telemetry adapter — calls the Go telemetry microservice over JSON/REST.

Endpoints mirror ``docs/contracts/telemetry.openapi.yaml`` exactly (field names are snake_case on
both sides), so request/response models serialize 1:1.
"""

from __future__ import annotations

from aql.adapters.tools._http import HttpJsonClient
from aql.domain.exceptions import ToolError
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

__all__ = ["HttpTelemetryClient"]


class HttpTelemetryClient:
    """A :class:`~aql.adapters.tools.base.TelemetryClient` backed by the Go service."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float = 10.0,
        max_retries: int = 2,
        backoff_s: float = 0.2,
    ) -> None:
        self._http = HttpJsonClient(
            base_url, timeout_s=timeout_s, max_retries=max_retries, backoff_s=backoff_s
        )

    async def search_logs(self, args: SearchLogsArgs) -> SearchLogsResult:
        data = await self._http.post("/v1/logs:search", args.model_dump(mode="json"))
        return SearchLogsResult.model_validate(data)

    async def query_metrics(self, args: QueryMetricsArgs) -> QueryMetricsResult:
        data = await self._http.post("/v1/metrics:query", args.model_dump(mode="json"))
        return QueryMetricsResult.model_validate(data)

    async def read_runbook(self, args: ReadRunbookArgs) -> RunbookResult:
        params = {"section": args.section} if args.section else None
        data = await self._http.get(f"/v1/runbooks/{args.slug}", params=params)
        return RunbookResult.model_validate(data)

    async def open_ticket(self, args: OpenTicketArgs) -> OpenTicketResult:
        data = await self._http.post("/v1/tickets", args.model_dump(mode="json"))
        return OpenTicketResult.model_validate(data)

    async def healthy(self) -> bool:
        try:
            data = await self._http.get("/healthz")
        except ToolError:
            return False
        return data.get("status") == "ok"

    async def aclose(self) -> None:
        await self._http.aclose()
