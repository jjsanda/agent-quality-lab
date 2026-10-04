"""Contract tests for the HTTP telemetry adapter against a respx-mocked Go service.

These pin the request shape and response parsing without a live service, and cover the retry /
error behaviour of the shared HTTP helper.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from aql.adapters.tools.telemetry_http import HttpTelemetryClient
from aql.domain.exceptions import ToolError
from aql.domain.incidents import Severity
from aql.domain.tools_schema import (
    OpenTicketArgs,
    QueryMetricsArgs,
    ReadRunbookArgs,
    SearchLogsArgs,
)

pytestmark = pytest.mark.integration

BASE = "http://telemetry.local"


@respx.mock
async def test_search_logs_over_http() -> None:
    route = respx.post(f"{BASE}/v1/logs:search").mock(
        return_value=httpx.Response(
            200,
            json={
                "lines": [
                    {
                        "timestamp": "2026-06-30T11:00:00Z",
                        "level": "ERROR",
                        "service": "checkout",
                        "message": "boom",
                        "trace_id": "t1",
                    }
                ],
                "total_matched": 1,
                "truncated": False,
            },
        )
    )
    client = HttpTelemetryClient(BASE)
    result = await client.search_logs(SearchLogsArgs(service="checkout", query="ERROR"))
    assert result.total_matched == 1
    assert result.lines[0].message == "boom"
    assert route.called
    await client.aclose()


@respx.mock
async def test_metrics_runbook_and_ticket() -> None:
    respx.post(f"{BASE}/v1/metrics:query").mock(
        return_value=httpx.Response(
            200,
            json={
                "metric": "latency_p99_ms",
                "unit": "ms",
                "aggregation": "p99",
                "series": [{"t": "2026-06-30T11:00:00Z", "v": 2100.0}],
            },
        )
    )
    respx.get(f"{BASE}/v1/runbooks/latency-troubleshooting").mock(
        return_value=httpx.Response(
            200,
            json={
                "slug": "latency-troubleshooting",
                "title": "Latency",
                "content": "x",
                "version": "v3",
            },
        )
    )
    respx.post(f"{BASE}/v1/tickets").mock(
        return_value=httpx.Response(
            201, json={"ticket_id": "TCK-1001", "url": "https://t/1001", "status": "escalated"}
        )
    )
    client = HttpTelemetryClient(BASE)
    metrics = await client.query_metrics(
        QueryMetricsArgs(service="checkout", metric="latency_p99_ms", aggregation="p99")
    )
    assert metrics.unit == "ms" and len(metrics.series) == 1
    runbook = await client.read_runbook(ReadRunbookArgs(slug="latency-troubleshooting"))
    assert runbook.version == "v3"
    ticket = await client.open_ticket(
        OpenTicketArgs(
            title="t", service="checkout", severity=Severity.SEV1, body="b", escalate=True
        )
    )
    assert ticket.status == "escalated"
    await client.aclose()


@respx.mock
async def test_4xx_raises_tool_error() -> None:
    respx.get(f"{BASE}/v1/runbooks/missing").mock(
        return_value=httpx.Response(404, json={"error": "x"})
    )
    client = HttpTelemetryClient(BASE)
    with pytest.raises(ToolError):
        await client.read_runbook(ReadRunbookArgs(slug="missing"))
    await client.aclose()


@respx.mock
async def test_5xx_is_retried_then_succeeds() -> None:
    route = respx.post(f"{BASE}/v1/logs:search").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json={"lines": [], "total_matched": 0, "truncated": False}),
        ]
    )
    client = HttpTelemetryClient(BASE, backoff_s=0.0)
    result = await client.search_logs(SearchLogsArgs(service="checkout", query="x"))
    assert result.total_matched == 0
    assert route.call_count == 2
    await client.aclose()


@respx.mock
async def test_healthy_reflects_backend() -> None:
    respx.get(f"{BASE}/healthz").mock(return_value=httpx.Response(200, json={"status": "ok"}))
    client = HttpTelemetryClient(BASE)
    assert await client.healthy() is True
    await client.aclose()


@respx.mock
async def test_healthy_false_on_error() -> None:
    respx.get(f"{BASE}/healthz").mock(return_value=httpx.Response(503))
    client = HttpTelemetryClient(BASE, backoff_s=0.0)
    assert await client.healthy() is False
    await client.aclose()
