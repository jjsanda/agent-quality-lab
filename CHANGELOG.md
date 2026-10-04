# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release of `agent-quality-lab`:
  - LangGraph incident-response agent (`plan → act → validate → retry → synthesize → finalize`, with a guarded `refuse` path).
  - Structured outputs (Pydantic v2): incident classification, tool calls, remediation plans.
  - Sandboxed tool layer (`search_logs`, `query_metrics`, `read_runbook`, `open_ticket`) behind a swappable transport port (in-process fake / HTTP).
  - Guardrails: schema validation, bounded retry-with-feedback, unsafe-action refusal, and a prompt-injection corpus.
  - Deterministic offline stack (scripted LLM + fake telemetry) plus a real Anthropic Claude adapter.
  - Go telemetry/runbook microservice (HTTP/REST + OpenAPI), OpenTelemetry-instrumented.
  - Evaluation harness with a CI pass/fail gate (accuracy, tool-call precision/recall, injection-resistance, latency, cost) emitting a machine-readable + Markdown report.
  - Full local observability stack (OTel Collector → Jaeger + Prometheus + Grafana).

[Unreleased]: https://github.com/jjsanda/agent-quality-lab/commits/main
