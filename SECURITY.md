# Security Policy

## Reporting a vulnerability

This is a portfolio/demo project. If you spot a security issue, please open a GitHub issue describing it (omit any exploit details that would put users at risk) or contact the author.

## Threat model & design choices

`agent-quality-lab` runs an LLM-driven agent, so it is built defensively from the ground up. The guardrails are a first-class part of the design, not an afterthought:

- **No destructive tool surface.** The agent can only *read* telemetry (`search_logs`, `query_metrics`, `read_runbook`) and *file* a ticket (`open_ticket`). There is deliberately **no** `restart_service`, `delete`, `scale`, or shell tool. Remediation is **advisory** — the worst a fully-compromised or prompt-injected model can do is read mock data and open a ticket.
- **Sandboxed tool calls.** Every tool call is allowlisted, its arguments are validated against a strict Pydantic schema (`extra="forbid"`), bounded in size, and run under a timeout before it reaches any transport.
- **Prompt-injection resistance.** Tool *results* (logs, runbooks) are treated as untrusted data. Injected directives ("ignore previous instructions", "curl … | sh", "drop the database") are detected by the safety policy; the agent refuses and escalates instead of complying. A corpus of injection fixtures is scored on every CI run (`injection_resistance`, gated at 1.00).
- **No secrets in the repo.** API keys are read only from the environment (`ANTHROPIC_API_KEY`); the default stack needs none.
- **Dependency hygiene.** `pip-audit` (Python) and Trivy (filesystem) run in CI.

See [`docs/adr/`](docs/adr/) for the architecture decision records behind these choices.
