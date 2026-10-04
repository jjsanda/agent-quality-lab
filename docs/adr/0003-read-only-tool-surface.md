# ADR 0003 — Read-only tool surface (safety by construction)

**Status:** accepted

## Context

The agent consumes untrusted data (logs, runbooks) that can carry prompt-injection. Guardrails that rely only on detecting bad instructions are a single line of defense.

## Decision

Make the tool surface **read-only telemetry plus `open_ticket`** — `search_logs`, `query_metrics`, `read_runbook`, `open_ticket`. There is deliberately **no** `restart_service`, `delete`, `scale`, or shell tool. Remediation is *advisory*: the agent proposes a `RemediationPlan` for a human, it never executes changes. Every tool call still passes through the `ToolExecutor` sandbox (allowlist, strict arg-validation, safety policy, timeout, size cap).

## Consequences

- The worst a fully-compromised or injected model can do is read mock data and file a ticket.
- The prompt-injection detector in the policy is defense *in depth*, not the only line — so an un-caught injection still cannot cause damage.
- Extending the agent to *act* would require adding a gated, approval-bound tool and re-evaluating this decision.
