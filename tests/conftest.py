"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from aql.adapters.clock import FixedClock, SequentialIdGenerator
from aql.adapters.tools.executor import ToolExecutor
from aql.adapters.tools.telemetry_fake import FakeTelemetryClient
from aql.domain.incidents import IncidentInput

# A fixed instant + repo data dir so every test that needs time/fixtures is deterministic.
FIXED_NOW = datetime(2026, 6, 30, 11, 2, 0, tzinfo=UTC)
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture
def incident() -> IncidentInput:
    """A representative incident used across the test suite."""
    return IncidentInput(
        id="INC-4471",
        title="Checkout p99 latency breached SLO",
        description="Checkout service p99 latency > 2s for 10 minutes.",
        service="checkout",
        signal="alert: checkout p99 > 2000ms",
        received_at=FIXED_NOW,
    )


@pytest.fixture
def data_dir() -> Path:
    return DATA_DIR


@pytest.fixture
def fixed_clock() -> FixedClock:
    return FixedClock(FIXED_NOW)


@pytest.fixture
def seq_ids() -> SequentialIdGenerator:
    return SequentialIdGenerator()


@pytest.fixture
def fake_client(seq_ids: SequentialIdGenerator) -> FakeTelemetryClient:
    return FakeTelemetryClient(data_dir=DATA_DIR, id_gen=seq_ids)


@pytest.fixture
def executor(
    fake_client: FakeTelemetryClient,
    fixed_clock: FixedClock,
    seq_ids: SequentialIdGenerator,
) -> ToolExecutor:
    return ToolExecutor(fake_client, clock=fixed_clock, id_gen=seq_ids)
