# Evaluation harness

A CI-enforced quality gate for the agent. `make eval` runs the agent over the golden dataset on the fully-offline deterministic stack, scores it, writes `results.json` + `results.md`, and exits non-zero if any metric breaches [`thresholds.yaml`](thresholds.yaml) — so a regression fails the build.

## Design

The golden scenarios (`golden/*.yaml`) provide **inputs and expected outcomes only**. The agent's behaviour is produced independently by the engine and then *scored against* those expectations, so the numbers measure real quality — not a replayed script. Two scenarios contain deliberate classification challenges, so accuracy lands realistically below 1.0.

Thresholds sit a margin **below** the engine's achieved values, acting as regression guards rather than aspirational targets. Injection-resistance and unsafe-refusal are gated at **1.00** (zero tolerance); over-refusal of benign incidents is capped.

## Metrics

| metric | meaning |
| --- | --- |
| `classification_accuracy` | severity **and** category both correct (triage scenarios) |
| `category_accuracy` / `severity_within_1` | category exact / severity within one level |
| `outcome_accuracy` | produced a plan vs. refused, as expected |
| `tool_recall` / `trace_match` | gathered the expected evidence, in order |
| `injection_resistance` | emitted **no** destructive/injected action on injection scenarios |
| `unsafe_refusal_rate` | refused every genuinely-unsafe request |
| `false_refusal_rate` | refused a *benign* incident (lower is better) |
| `plan_validity` | plan is schema-valid, has a rollback, no unapproved destructive step |

Latency, token, and cost figures are reported (not gated); the cost is estimated at `claude-opus-4-8` rates for illustration — offline runs are free.

## Live evaluation

`make eval-live` runs the same harness against the real Claude API on the `smoke`-tagged subset (needs `ANTHROPIC_API_KEY`), for genuine accuracy/latency/cost numbers.
