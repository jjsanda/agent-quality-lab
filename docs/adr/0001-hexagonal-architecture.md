# ADR 0001 — Hexagonal architecture

**Status:** accepted

## Context

The agent must swap its LLM (a real API vs. a deterministic offline engine) and its telemetry transport (in-process vs. a network service) without those choices leaking into the reasoning logic. It also needs a core that is trivially unit-testable.

## Decision

Use ports & adapters. `aql.domain` is framework-free (only stdlib + Pydantic) and defines the run state, schemas, and safety policy. The LangGraph state machine (`aql.graph`) depends on two `typing.Protocol` ports — `LLMEngine` and `TelemetryClient` — never on concrete adapters. Concrete adapters live under `aql.adapters`, and `aql.factory` is the single composition root that selects and wires them from `Settings`.

## Consequences

- Swapping deterministic ⇄ Claude or fake ⇄ HTTP is a one-line change in the factory; the graph is identical in every mode.
- The domain core has ~100% test coverage with no mocks.
- The cost is a little ceremony (ports, a factory) that pays off the moment a second adapter exists — which it does (two LLM engines, two transports).
