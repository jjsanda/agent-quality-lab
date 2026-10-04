"""Typed exceptions for the agent harness.

A small, explicit hierarchy lets callers (the graph nodes, the CLI, the eval harness)
distinguish a misconfiguration from a guardrail trip from a transient provider failure.
"""

from __future__ import annotations

__all__ = [
    "AqlError",
    "ConfigError",
    "ToolError",
    "GuardrailViolationError",
    "ProviderUnavailableError",
    "ScenarioError",
]


class AqlError(Exception):
    """Base class for every error raised by ``aql``."""


class ConfigError(AqlError):
    """Invalid or insufficient configuration (e.g. a real provider selected without a key)."""


class ToolError(AqlError):
    """A tool call could not be executed (transport failure, timeout, malformed result)."""


class GuardrailViolationError(AqlError):
    """A guardrail refused an action (unsafe tool call or unsafe remediation plan)."""


class ProviderUnavailableError(AqlError):
    """A real LLM provider was unreachable or returned a terminal error."""


class ScenarioError(AqlError):
    """The deterministic scripted engine was asked for a turn it has no script for."""
