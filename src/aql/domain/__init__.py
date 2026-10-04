"""The framework-free core of the hexagon.

These modules define *what the agent reasons about* — incidents, tool contracts, remediation
plans, the safety policy, and the run state — using nothing but the standard library and
Pydantic. They import no LangGraph, no Anthropic SDK, no httpx, and no OpenTelemetry, so the
domain is trivially unit-testable and the same rules apply identically in offline and live modes.
"""

from __future__ import annotations
