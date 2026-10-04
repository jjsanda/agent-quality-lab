# Build spec

The guiding specification this repository was built to, preserved as an artifact.

## Goal

A **production-style AI agent reliability harness** for an engineering-support ("SRE on-call") agent that can inspect logs, query metrics, search docs, and propose remediation — focused on agent-*systems* engineering (loops, tool use, structured outputs, validation, observability, measurable quality), not prompt-tweaking. It must be understandable to non-technical readers via clear diagrams, and run offline with no API key.

## Scope

| Area | What was built |
| --- | --- |
| Python agent layer | LangGraph state machine with explicit nodes for planning, tool use, validation, retry, and final answer, plus a guarded refuse path. |
| Tool-calling | `search_logs`, `query_metrics`, `read_runbook`, `open_ticket`, sandboxed behind a swappable transport port. |
| Structured outputs | Pydantic v2 / JSON-schema for tool calls, incident classification, remediation plans. |
| Guardrails | Output validation, bounded retry-with-feedback, refusal on unsafe/injected actions, prompt-injection fixtures. |
| Evaluation | Golden dataset, expected outcomes, regression metrics, pass/fail CI gate, self-updating report. |
| Go component | Go microservice exposing mock telemetry/runbook APIs over HTTP/REST + OpenAPI. |
| Observability | OpenTelemetry traces (GenAI semconv) + latency/cost/error metrics → Collector → Jaeger/Prometheus/Grafana. |
| Professional polish | Evaluation report in the README (accuracy, tool-call precision, failure cases, tradeoffs); ADRs; diagrams. |

## Non-negotiables

- **Offline-first & deterministic:** clones and passes CI with no API key; the same run is byte-reproducible.
- **Real provider behind a port:** Anthropic Claude selectable by env var, identical graph.
- **Safety by construction:** read-only tool surface + advisory remediation; injection-resistance and unsafe-refusal gated at 1.00.
- **House style:** `uv`, hexagonal architecture, `mypy --strict`, ~90% coverage gate, Docker, GitHub Actions.

## How to verify

`make setup && make lint && make type && make test-cov && make eval && make go-test`, then `aql diagnose data/incidents/checkout-latency.json` (a plan) and `.../poisoned-incident.json` (a refusal). `make up` / `make demo` brings up the observability stack and produces a live trace.
