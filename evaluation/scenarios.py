"""Golden-dataset loading: one YAML scenario per file (input incident + expectations).

The scenarios provide *inputs and expected outcomes only* — the agent's behaviour is produced
independently by the engine and then scored against them, so the evaluation measures real quality
rather than replaying a script.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from aql.domain.incidents import IncidentCategory, IncidentInput, Severity

__all__ = ["Expected", "Scenario", "load_scenarios", "GOLDEN_DIR"]

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


class Expected(BaseModel):
    """What a competent SRE would expect the agent to do."""

    model_config = ConfigDict(extra="forbid")

    outcome: Literal["plan", "refuse"] = "plan"
    severity: Severity
    category: IncidentCategory
    tool_trace: list[str] = Field(default_factory=list)


class Scenario(BaseModel):
    """One evaluation case."""

    model_config = ConfigDict(extra="forbid")

    id: str
    tags: list[str] = Field(default_factory=list)
    incident: IncidentInput
    expected: Expected


def load_scenarios(directory: Path = GOLDEN_DIR) -> list[Scenario]:
    """Load and validate every ``*.yaml`` scenario under ``directory`` (sorted by filename)."""
    scenarios = [
        Scenario.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        for path in sorted(directory.glob("*.yaml"))
    ]
    if not scenarios:
        raise FileNotFoundError(f"no golden scenarios found in {directory}")
    return scenarios
