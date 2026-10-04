# Fixtures

Deterministic data for the offline stack and the evaluation harness.

- **`incidents/`** — sample `IncidentInput` payloads for `aql diagnose`:
  - `checkout-latency.json` — a benign latency incident (the happy-path demo).
  - `payments-errors.json` — an error-rate incident.
  - `cart-injection.json` — a benign incident whose **logs contain prompt-injection**, so the agent reads hostile text but must not act on it (injection-resistance demo).
  - `poisoned-incident.json` — the **incident text itself** carries an injected destructive directive; the agent must refuse and escalate (refusal demo).
- **`runbooks/`** — one Markdown runbook per failure mode, plus `untrusted-vendor-runbook.md`, a deliberately **poisoned** runbook used only by the live demo to show the guardrails refusing it.
- **`telemetry/logs.json`** — seeded log lines per service. The `cart` service's lines include two embedded injection attempts. Metric series are generated deterministically in code, not stored.

Nothing here is real customer data.
