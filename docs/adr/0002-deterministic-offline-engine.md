# ADR 0002 — A deterministic engine as the offline default

**Status:** accepted

## Context

An LLM-powered project that only runs with an API key is hard to review, hard to test, and impossible to gate in CI reproducibly. But a mock that simply *replays the expected answer* makes any evaluation tautological (it would score 100% by construction).

## Decision

Ship a `DeterministicLLMEngine`: a rule-based "agent brain" that derives classification, tool calls, and a safe templated remediation plan **from the incident itself** — not from the eval's expected outcomes. It is the default engine and the only one used in CI/eval. A real `AnthropicLLMEngine` (forced tool-use structured output) plugs in behind the same port for live runs. The same Pydantic validators run on both paths.

## Consequences

- The whole harness — including the quality gate — runs offline with no key, byte-reproducibly.
- The evaluation measures *real* behaviour and lands realistically below 1.0, because the engine's outputs are independent of the expectations.
- The offline engine isn't as capable as a real model; that gap is covered by `make eval-live` and an Anthropic request-shape contract test that runs in CI without a key.
