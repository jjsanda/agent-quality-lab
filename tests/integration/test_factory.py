"""Integration tests for the composition root."""

from __future__ import annotations

import pytest

from aql.adapters.llm.deterministic import DeterministicLLMEngine
from aql.adapters.tools.telemetry_fake import FakeTelemetryClient
from aql.adapters.tools.telemetry_http import HttpTelemetryClient
from aql.config.settings import Settings
from aql.domain.exceptions import ConfigError
from aql.factory import build_services

pytestmark = pytest.mark.integration


def test_offline_defaults_wire_deterministic_fake() -> None:
    services = build_services(Settings(_env_file=None))
    assert isinstance(services.engine, DeterministicLLMEngine)
    assert isinstance(services.telemetry, FakeTelemetryClient)


def test_http_transport_selected() -> None:
    services = build_services(Settings(_env_file=None, transport="http"))
    assert isinstance(services.telemetry, HttpTelemetryClient)


def test_anthropic_without_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AQL_ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ConfigError):
        build_services(Settings(_env_file=None, llm_provider="anthropic"))
