"""agent-quality-lab (``aql``): a reliability harness for an LLM incident-response agent.

The package is organised as a hexagon. The framework-free core lives in :mod:`aql.domain`
(schemas, the safety policy, prompts). The LangGraph state machine that orchestrates the
agent lives in :mod:`aql.graph`. Everything that touches the outside world — the LLM, the
telemetry transport, OpenTelemetry — is an adapter under :mod:`aql.adapters` /
:mod:`aql.observability`, selected and wired by the composition root :mod:`aql.factory`.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
