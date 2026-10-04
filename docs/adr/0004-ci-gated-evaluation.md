# ADR 0004 — CI-gated evaluation

**Status:** accepted

## Context

"The agent seems good" is not a claim you can defend or maintain. Agent quality regresses silently when prompts, tools, or models change.

## Decision

Treat agent quality like test coverage. A golden dataset (`evaluation/golden/*.yaml`) of inputs + expected outcomes is scored by pure, auditable metric math into accuracy, tool precision/recall, injection-resistance, refusal rates, latency, and cost. `make eval` compares the summary to `thresholds.yaml` and exits non-zero on any breach, so a regression **fails the build**. It emits `results.json` (machine) and a `results.md` fragment injected into the README (headline numbers are always CI-generated). Thresholds sit a margin below achieved values, acting as regression guards. Injection-resistance and unsafe-refusal are gated at 1.00 (zero tolerance).

## Consequences

- Quality is visible, defensible, and protected from regression.
- The gate proves the agent didn't get *worse* — not that it's optimal; the golden set must grow.
- Latency is reported but not gated (it's non-deterministic); the gated quality metrics are byte-reproducible.
