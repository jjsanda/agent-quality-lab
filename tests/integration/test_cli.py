"""Integration tests for the CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aql.cli import main

pytestmark = pytest.mark.integration

_REPO = Path(__file__).resolve().parents[2]


def test_info_prints_config(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["info"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["llm_provider"] == "deterministic"


def test_diagnose_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    incident = _REPO / "data" / "incidents" / "checkout-latency.json"
    assert main(["diagnose", str(incident), "--json"]) == 0
    state = json.loads(capsys.readouterr().out)
    assert state["remediation"] is not None
    assert state["refusal"] is None


def test_diagnose_poisoned_refuses(capsys: pytest.CaptureFixture[str]) -> None:
    incident = _REPO / "data" / "incidents" / "poisoned-incident.json"
    assert main(["diagnose", str(incident), "--json"]) == 0
    state = json.loads(capsys.readouterr().out)
    assert state["refusal"] is not None
    assert state["remediation"] is None


def test_diagnose_rich_plan(capsys: pytest.CaptureFixture[str]) -> None:
    incident = _REPO / "data" / "incidents" / "checkout-latency.json"
    assert main(["diagnose", str(incident)]) == 0
    assert "Remediation plan" in capsys.readouterr().out


def test_diagnose_rich_refusal(capsys: pytest.CaptureFixture[str]) -> None:
    incident = _REPO / "data" / "incidents" / "poisoned-incident.json"
    assert main(["diagnose", str(incident)]) == 0
    assert "REFUSED" in capsys.readouterr().out
