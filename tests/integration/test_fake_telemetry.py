"""Integration tests for the deterministic fake telemetry client."""

from __future__ import annotations

import pytest

from aql.adapters.tools.telemetry_fake import FakeTelemetryClient
from aql.domain.incidents import Severity
from aql.domain.tools_schema import (
    OpenTicketArgs,
    QueryMetricsArgs,
    ReadRunbookArgs,
    SearchLogsArgs,
)

pytestmark = pytest.mark.integration


class TestFakeTelemetry:
    async def test_search_logs_filters_and_counts(self, fake_client: FakeTelemetryClient) -> None:
        result = await fake_client.search_logs(SearchLogsArgs(service="checkout", query="pool"))
        assert result.total_matched >= 1
        assert all("pool" in line.message.lower() for line in result.lines)

    async def test_search_logs_limit_truncates(self, fake_client: FakeTelemetryClient) -> None:
        result = await fake_client.search_logs(
            SearchLogsArgs(service="checkout", query="e", limit=1)
        )
        assert len(result.lines) == 1
        assert result.total_matched > 1
        assert result.truncated is True

    async def test_metric_series_is_deterministic(self, fake_client: FakeTelemetryClient) -> None:
        args = QueryMetricsArgs(service="checkout", metric="latency_p99_ms", aggregation="p99")
        first = await fake_client.query_metrics(args)
        second = await fake_client.query_metrics(args)
        assert first == second
        assert first.unit == "ms"
        assert len(first.series) == 12

    async def test_read_runbook_and_fallback(self, fake_client: FakeTelemetryClient) -> None:
        runbook = await fake_client.read_runbook(ReadRunbookArgs(slug="latency-troubleshooting"))
        assert "Latency" in runbook.title

        missing = await fake_client.read_runbook(ReadRunbookArgs(slug="does-not-exist"))
        assert missing.slug == "does-not-exist"  # falls back to the general runbook's content
        assert "Incident Response" in missing.title

    async def test_open_ticket_open_vs_escalated(self, fake_client: FakeTelemetryClient) -> None:
        opened = await fake_client.open_ticket(
            OpenTicketArgs(title="t", service="checkout", severity=Severity.SEV2, body="b")
        )
        assert opened.status == "open"
        assert opened.ticket_id.startswith("TCK-")

        escalated = await fake_client.open_ticket(
            OpenTicketArgs(
                title="t", service="checkout", severity=Severity.SEV1, body="b", escalate=True
            )
        )
        assert escalated.status == "escalated"

    async def test_healthy(self, fake_client: FakeTelemetryClient) -> None:
        assert await fake_client.healthy() is True
        await fake_client.aclose()
