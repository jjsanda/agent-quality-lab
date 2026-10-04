"""Concrete :class:`~aql.domain.clock.Clock` and :class:`~aql.domain.clock.IdGenerator`.

The ``System*`` / ``Uuid*`` variants are used in live runs; the ``Fixed`` / ``Sequential``
variants make offline and eval runs byte-for-byte reproducible.
"""

from __future__ import annotations

import itertools
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

__all__ = ["SystemClock", "FixedClock", "UuidGenerator", "SequentialIdGenerator"]


class SystemClock:
    """Wall-clock UTC time (live mode)."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """Always returns the same instant (offline/eval mode)."""

    def __init__(self, instant: datetime) -> None:
        self._instant = instant

    def now(self) -> datetime:
        return self._instant


class UuidGenerator:
    """Random short ids (live mode)."""

    def new_id(self, prefix: str = "") -> str:
        token = uuid.uuid4().hex[:12]
        return f"{prefix}{token}" if prefix else token


class SequentialIdGenerator:
    """Deterministic monotonic ids, e.g. ``tc-1``, ``tc-2`` (offline/eval mode)."""

    def __init__(self, *, start: int = 1) -> None:
        self._counter: Iterator[int] = itertools.count(start)

    def new_id(self, prefix: str = "") -> str:
        value = next(self._counter)
        return f"{prefix}{value}" if prefix else str(value)
