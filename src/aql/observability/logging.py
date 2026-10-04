"""Structured logging via ``structlog`` (JSON by default)."""

from __future__ import annotations

import logging
from typing import Any

import structlog

__all__ = ["configure_logging", "get_logger"]


def configure_logging(*, level: str = "INFO", json: bool = True) -> None:
    """Configure ``structlog`` for the process. Idempotent enough for CLI/eval entry points."""
    numeric = getattr(logging, level.upper(), logging.INFO)
    renderer: Any = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> Any:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)
