"""Opt-in OpenTelemetry tracing (gated by ``AQL_OTEL_ENABLED``; needs the ``otel`` extra).

Kept lazily imported so the default install carries no OpenTelemetry dependency. When enabled it
wires an OTLP/HTTP exporter (to the local collector) and publishes a module-level tracer that the
graph's node wrapper picks up; when disabled, every tracing hook is a no-op.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from aql.config.settings import Settings

logger = logging.getLogger(__name__)

__all__ = ["configure_tracing", "get_tracer"]

_tracer: Any = None


def configure_tracing(settings: Settings) -> Any | None:
    """Set up an OTLP tracer provider if tracing is enabled and the SDK is installed."""
    global _tracer
    if not settings.otel_enabled:
        return None
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning(
            "AQL_OTEL_ENABLED is set but opentelemetry is not installed (the 'otel' extra)"
        )
        return None

    import atexit

    resource = Resource.create({"service.name": settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=f"{settings.otel_exporter_otlp_endpoint}/v1/traces")
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    atexit.register(provider.shutdown)  # flush the batch processor for short-lived CLI/eval runs
    _tracer = trace.get_tracer("aql")
    logger.info("OpenTelemetry tracing enabled (service=%s)", settings.otel_service_name)
    return provider


def get_tracer() -> Any:
    """Return the configured tracer, or ``None`` when tracing is disabled."""
    return _tracer
