"""Unit tests for the clock / id-generator adapters."""

from __future__ import annotations

from datetime import UTC, datetime

from aql.adapters.clock import FixedClock, SequentialIdGenerator, SystemClock, UuidGenerator
from aql.domain.clock import Clock, IdGenerator


def test_fixed_clock_is_constant_and_satisfies_port() -> None:
    instant = datetime(2026, 6, 30, 11, 0, tzinfo=UTC)
    clock = FixedClock(instant)
    assert isinstance(clock, Clock)
    assert clock.now() == instant == clock.now()


def test_system_clock_is_timezone_aware() -> None:
    assert SystemClock().now().tzinfo is not None


def test_sequential_id_generator_is_monotonic() -> None:
    gen = SequentialIdGenerator()
    assert isinstance(gen, IdGenerator)
    assert [gen.new_id("tc-") for _ in range(3)] == ["tc-1", "tc-2", "tc-3"]


def test_uuid_generator_is_unique_and_prefixed() -> None:
    gen = UuidGenerator()
    a, b = gen.new_id("tk-"), gen.new_id("tk-")
    assert a.startswith("tk-") and b.startswith("tk-") and a != b
