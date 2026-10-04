# ADR 0005 — OpenTelemetry GenAI-semconv tracing

**Status:** accepted

## Context

For an agent, latency, cost, and where-it-went-wrong are operational questions. They should be answered with telemetry, not print statements.

## Decision

Instrument the agent with OpenTelemetry, opt-in via `AQL_OTEL_ENABLED`. Each run is a root `aql.diagnose` span with one child span per node; the LLM and tool ports emit `aql.llm.<provider>` and `aql.tool.<name>` spans carrying GenAI semantic-convention attributes (`gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`/`output_tokens`) and tool status/latency. Traces export over OTLP to a Collector → Jaeger; the Go service exposes Prometheus metrics; Grafana provisions dashboards. Everything is a no-op when tracing is disabled, so the default install carries no OpenTelemetry dependency.

## Consequences

- A single agent run renders as a connected 16-span waterfall in Jaeger; cost/latency are queryable.
- The OTLP pipeline is exactly what you'd repoint at a managed observability backend in production.
- Tracing hooks add a little code to the nodes; kept minimal and centralised in `graph/tracing.py`.
