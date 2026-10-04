"""Composition root: turn :class:`Settings` into a wired, runnable agent.

This is the only place that constructs adapters, so swapping the LLM engine (deterministic ↔
Claude) or the telemetry transport (fake ↔ HTTP) is a configuration change here, not a code change
anywhere in the graph. Offline runs (``transport=fake``) get the deterministic clock/id-generator
so a whole diagnosis is reproducible.

Example:
    >>> import asyncio
    >>> from aql.config.settings import Settings
    >>> from aql.domain.incidents import IncidentInput
    >>> from datetime import datetime, timezone
    >>> services = build_services(Settings(_env_file=None))
    >>> services.engine.provider, services.settings.transport
    ('deterministic', 'fake')
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, assert_never

from aql.adapters.clock import FixedClock, SequentialIdGenerator, SystemClock, UuidGenerator
from aql.adapters.llm.anthropic_engine import AnthropicLLMEngine
from aql.adapters.llm.base import LLMEngine
from aql.adapters.llm.deterministic import DeterministicLLMEngine
from aql.adapters.tools.base import TelemetryClient
from aql.adapters.tools.executor import ToolExecutor
from aql.adapters.tools.telemetry_fake import FakeTelemetryClient
from aql.adapters.tools.telemetry_http import HttpTelemetryClient
from aql.config.settings import Settings
from aql.domain.clock import Clock, IdGenerator
from aql.domain.exceptions import ConfigError
from aql.domain.incidents import IncidentInput
from aql.domain.state import AgentState
from aql.graph.build import build_graph
from aql.graph.tracing import child_span
from aql.observability.tracing import configure_tracing

__all__ = ["Services", "build_services", "run_diagnosis"]

logger = logging.getLogger(__name__)

# Reference instant for offline runs (matches the fake telemetry fixtures).
_FIXED_REF = datetime(2026, 6, 30, 11, 0, 0, tzinfo=UTC)


@dataclass(slots=True)
class Services:
    """The fully-wired agent handed to the CLI and eval harness."""

    settings: Settings
    clock: Clock
    id_gen: IdGenerator
    engine: LLMEngine
    telemetry: TelemetryClient
    executor: ToolExecutor
    graph: Any

    async def aclose(self) -> None:
        """Release network resources held by the LLM engine and the transport (best-effort)."""
        await self.engine.aclose()
        await self.telemetry.aclose()


def _build_clock_and_ids(settings: Settings) -> tuple[Clock, IdGenerator]:
    if settings.transport == "fake":
        return FixedClock(_FIXED_REF), SequentialIdGenerator()
    return SystemClock(), UuidGenerator()


def _build_engine(settings: Settings) -> LLMEngine:
    provider = settings.llm_provider
    if provider == "deterministic":
        return DeterministicLLMEngine()
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ConfigError("AQL_LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY")
        return AnthropicLLMEngine(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
            timeout_s=settings.request_timeout_s,
        )
    assert_never(provider)


def _build_telemetry(settings: Settings, id_gen: IdGenerator) -> TelemetryClient:
    transport = settings.transport
    if transport == "fake":
        return FakeTelemetryClient(data_dir=Path(settings.data_dir), id_gen=id_gen)
    if transport == "http":
        return HttpTelemetryClient(
            settings.telemetry_base_url, timeout_s=settings.request_timeout_s
        )
    assert_never(transport)


def build_services(settings: Settings) -> Services:
    """Build and wire every adapter and the compiled graph from configuration."""
    configure_tracing(settings)
    clock, id_gen = _build_clock_and_ids(settings)
    engine = _build_engine(settings)
    telemetry = _build_telemetry(settings, id_gen)
    executor = ToolExecutor(
        telemetry, clock=clock, id_gen=id_gen, timeout_s=settings.request_timeout_s
    )
    graph = build_graph(engine, executor)
    logger.info(
        "services built: provider=%s transport=%s", settings.llm_provider, settings.transport
    )
    return Services(
        settings=settings,
        clock=clock,
        id_gen=id_gen,
        engine=engine,
        telemetry=telemetry,
        executor=executor,
        graph=graph,
    )


async def run_diagnosis(services: Services, incident: IncidentInput) -> AgentState:
    """Run the agent graph over an incident and return the final :class:`AgentState`."""
    initial = AgentState(
        incident=incident, budget=services.settings.budget(), scenario_id=incident.id
    )
    with child_span(
        "aql.diagnose",
        **{"incident.id": incident.id, "incident.service": incident.service},
    ):
        raw = await services.graph.ainvoke(initial)
    return raw if isinstance(raw, AgentState) else AgentState.model_validate(raw)
