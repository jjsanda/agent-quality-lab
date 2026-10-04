"""Time and identity *ports* — the seams that make a run reproducible.

Anything in the agent that would otherwise reach for ``datetime.now()`` or ``uuid4()`` goes
through one of these instead. The offline/eval stack injects deterministic implementations
(:class:`~aql.adapters.clock.FixedClock`, :class:`~aql.adapters.clock.SequentialIdGenerator`)
so a whole agent run — including tool-call ids and timestamps — is byte-for-byte stable; the
live stack injects the wall-clock/UUID versions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

__all__ = ["Clock", "IdGenerator"]


@runtime_checkable
class Clock(Protocol):
    """Source of the current time (UTC-aware ``datetime``)."""

    def now(self) -> datetime:
        """Return the current instant as a timezone-aware ``datetime``."""


@runtime_checkable
class IdGenerator(Protocol):
    """Source of unique identifiers for tool calls and tickets."""

    def new_id(self, prefix: str = "") -> str:
        """Return a fresh identifier, optionally namespaced by ``prefix``."""
