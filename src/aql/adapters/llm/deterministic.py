"""The deterministic, rule-based "agent brain" — the offline default engine.

This is what makes the whole harness reproducible with no API key. It classifies an incident
and chooses tool calls from keyword rules, and synthesizes a safe, reversible remediation plan
from per-category templates grounded in the gathered evidence. Crucially it derives its outputs
*from the incident*, not from the eval's expected answers — so the evaluation measures real
behavior (and lands below a perfect score), rather than replaying a canned script.

By construction it never copies tool-output text into commands, so it ignores prompt-injection
in runbooks/logs rather than acting on it. Token usage is estimated deterministically from
prompt/output length so cost metrics are stable.
"""

from __future__ import annotations

from aql.adapters.llm.base import PlanOutput, PlanResult, SynthResult
from aql.domain.evidence import evidence_ref_from_result
from aql.domain.incidents import (
    IncidentCategory,
    IncidentClassification,
    IncidentInput,
    Severity,
)
from aql.domain.prompts import planner_user_prompt, synthesizer_user_prompt
from aql.domain.remediation import (
    EvidenceKind,
    EvidenceRef,
    RemediationPlan,
    RemediationStep,
    RiskLevel,
)
from aql.domain.state import TokenUsage
from aql.domain.tools_schema import ProposedToolCall, ToolName, ToolResult

__all__ = ["DeterministicLLMEngine"]

# Category detection, most-specific first. Each category wins by match count, ties broken by order.
_CATEGORY_KEYWORDS: tuple[tuple[IncidentCategory, tuple[str, ...]], ...] = (
    (
        IncidentCategory.CRASH_LOOP,
        ("crashloop", "crash loop", "crash-loop", "oomkill", "restarting", "restart loop"),
    ),
    (
        IncidentCategory.DEPLOY_REGRESSION,
        ("deploy", "rollout", "release", "regression", "canary", "new version"),
    ),
    (
        IncidentCategory.DEPENDENCY_OUTAGE,
        ("upstream", "downstream", "dependency", "connection refused", "unavailable", "outage"),
    ),
    (
        IncidentCategory.SATURATION,
        ("saturat", "cpu", "memory", "disk", "throttl", "exhaust", "capacity"),
    ),
    (
        IncidentCategory.ERROR_RATE,
        ("error rate", "5xx", "500s", "errors", "exception", "failed request", "error budget"),
    ),
    (
        IncidentCategory.LATENCY,
        ("latency", "slow", "p99", "p95", "p50", "response time", "timeout"),
    ),
    (IncidentCategory.DATA, ("corrupt", "inconsistent", "mismatch", "integrity", "stale data")),
)

_SEVERITY_KEYWORDS: tuple[tuple[Severity, tuple[str, ...]], ...] = (
    (
        Severity.SEV1,
        ("sev1", "sev-1", "outage", "is down", "all customers", "complete", "total", "everyone"),
    ),
    (Severity.SEV2, ("sev2", "sev-2", "breach", "elevated", "degraded", "partial")),
    (Severity.SEV3, ("sev3", "sev-3", "minor", "intermittent", "slight")),
)

_RUNBOOK_FOR_CATEGORY: dict[IncidentCategory, str] = {
    IncidentCategory.LATENCY: "latency-troubleshooting",
    IncidentCategory.ERROR_RATE: "error-rate-troubleshooting",
    IncidentCategory.SATURATION: "saturation-troubleshooting",
    IncidentCategory.CRASH_LOOP: "crash-loop-recovery",
    IncidentCategory.DEPLOY_REGRESSION: "deploy-rollback",
    IncidentCategory.DEPENDENCY_OUTAGE: "dependency-outage-response",
    IncidentCategory.DATA: "data-integrity-response",
    IncidentCategory.UNKNOWN: "general-incident-response",
}

_METRIC_FOR_CATEGORY: dict[IncidentCategory, tuple[str, str]] = {
    IncidentCategory.LATENCY: ("latency_p99_ms", "p99"),
    IncidentCategory.ERROR_RATE: ("error_rate", "rate"),
    IncidentCategory.SATURATION: ("cpu_saturation_pct", "max"),
    IncidentCategory.CRASH_LOOP: ("restart_count", "rate"),
    IncidentCategory.DEPLOY_REGRESSION: ("error_rate", "rate"),
    IncidentCategory.DEPENDENCY_OUTAGE: ("error_rate", "rate"),
    IncidentCategory.DATA: ("error_rate", "rate"),
    IncidentCategory.UNKNOWN: ("latency_p99_ms", "p99"),
}

_ROOT_CAUSE: dict[IncidentCategory, str] = {
    IncidentCategory.LATENCY: "Elevated latency, most likely resource contention or a slow dependency.",
    IncidentCategory.ERROR_RATE: "A rise in server-side errors, likely a bad release or a failing dependency.",
    IncidentCategory.SATURATION: "Resource saturation (CPU/memory) causing throttling and queueing.",
    IncidentCategory.CRASH_LOOP: "Pods crash-looping, most likely an OOM kill or a failed health check.",
    IncidentCategory.DEPLOY_REGRESSION: "A regression introduced by the most recent deployment.",
    IncidentCategory.DEPENDENCY_OUTAGE: "A failing upstream/downstream dependency degrading this service.",
    IncidentCategory.DATA: "A data integrity or consistency problem in the pipeline.",
    IncidentCategory.UNKNOWN: "Root cause not yet determined from the available signals.",
}

# Per-category step-2 mitigation: safe, reversible, never a catastrophic command.
_MITIGATION: dict[IncidentCategory, tuple[str, bool]] = {
    IncidentCategory.LATENCY: (
        "Scale {svc} out by one replica and raise the connection-pool size to relieve contention.",
        True,
    ),
    IncidentCategory.ERROR_RATE: (
        "Roll {svc} back to the previous known-good release and confirm the error rate recovers.",
        True,
    ),
    IncidentCategory.SATURATION: (
        "Add one replica to {svc} and raise its CPU request/limit to reduce throttling.",
        True,
    ),
    IncidentCategory.CRASH_LOOP: (
        "Raise the memory limit for {svc} and recreate the affected pods to break the crash loop.",
        True,
    ),
    IncidentCategory.DEPLOY_REGRESSION: (
        "Roll {svc} back to the previous known-good release.",
        True,
    ),
    IncidentCategory.DEPENDENCY_OUTAGE: (
        "Enable the circuit breaker / fallback for the failing dependency and retry with backoff.",
        False,
    ),
    IncidentCategory.DATA: (
        "Pause the affected data pipeline and reconcile from the last consistent checkpoint.",
        True,
    ),
    IncidentCategory.UNKNOWN: (
        "Gather additional diagnostics and page the service owner for hands-on triage.",
        False,
    ),
}


def _classify(incident: IncidentInput) -> IncidentClassification:
    text = f"{incident.title}\n{incident.signal}\n{incident.description}".lower()

    best_category, best_hits = IncidentCategory.UNKNOWN, 0
    for category, keywords in _CATEGORY_KEYWORDS:
        hits = sum(1 for kw in keywords if kw in text)
        if hits > best_hits:
            best_category, best_hits = category, hits

    severity = Severity.SEV2
    for candidate, keywords in _SEVERITY_KEYWORDS:
        if any(kw in text for kw in keywords):
            severity = candidate
            break

    confidence = round(min(0.9, 0.55 + 0.1 * best_hits), 2) if best_hits else 0.4
    return IncidentClassification(
        severity=severity,
        category=best_category,
        summary=incident.title[:280],
        affected_services=[incident.service],
        confidence=confidence,
        rationale=(
            f"Signal {incident.signal!r} and the description matched {best_hits} "
            f"{best_category.value} indicator(s)."
        ),
    )


def _tool_calls(
    incident: IncidentInput, classification: IncidentClassification
) -> list[ProposedToolCall]:
    metric, aggregation = _METRIC_FOR_CATEGORY[classification.category]
    slug = _RUNBOOK_FOR_CATEGORY[classification.category]
    return [
        ProposedToolCall(
            name=ToolName.SEARCH_LOGS,
            arguments={"service": incident.service, "query": "ERROR", "since": "30m", "limit": 100},
            reason="Find the most recent error signatures.",
        ),
        ProposedToolCall(
            name=ToolName.QUERY_METRICS,
            arguments={
                "service": incident.service,
                "metric": metric,
                "aggregation": aggregation,
                "since": "1h",
                "step": "5m",
            },
            reason=f"Quantify the {classification.category.value} signal.",
        ),
        ProposedToolCall(
            name=ToolName.READ_RUNBOOK,
            arguments={"slug": slug},
            reason="Pull the documented mitigation for this failure mode.",
        ),
    ]


def _references(tool_results: list[ToolResult], slug: str) -> list[EvidenceRef]:
    refs = [ref for r in tool_results if (ref := evidence_ref_from_result(r)) is not None]
    if not refs:  # always cite at least the runbook so the plan is grounded and schema-valid
        refs = [EvidenceRef(kind=EvidenceKind.RUNBOOK, ref=slug, tool_call_id="synthesized")]
    return refs


def _synthesize(
    incident: IncidentInput,
    classification: IncidentClassification,
    tool_results: list[ToolResult],
) -> RemediationPlan:
    category = classification.category
    svc = incident.service
    slug = _RUNBOOK_FOR_CATEGORY[category]
    metric, _ = _METRIC_FOR_CATEGORY[category]
    mitigation_text, needs_approval = _MITIGATION[category]
    references = _references(tool_results, slug)
    ref_ids = [r.ref for r in references][:6]

    steps = [
        RemediationStep(
            order=1,
            action=f"Review the top ERROR log signatures for {svc} from the last 30 minutes to confirm the failure mode.",
            evidence_refs=ref_ids,
        ),
        RemediationStep(
            order=2,
            action=mitigation_text.format(svc=svc),
            requires_approval=needs_approval,
            evidence_refs=ref_ids,
        ),
        RemediationStep(
            order=3,
            action=f"Apply the documented mitigation from the {slug!r} runbook and re-check the {metric} metric.",
            evidence_refs=ref_ids,
        ),
        RemediationStep(
            order=4,
            action="Monitor for 15 minutes; if the signal does not recover, escalate to the service owner.",
        ),
    ]
    risk = {Severity.SEV1: RiskLevel.HIGH, Severity.SEV2: RiskLevel.MEDIUM}.get(
        classification.severity, RiskLevel.LOW
    )
    return RemediationPlan(
        incident_summary=f"{classification.category.value} on {svc}: {incident.title}"[:400],
        root_cause_hypothesis=_ROOT_CAUSE[category],
        risk_level=risk,
        steps=steps,
        rollback=(
            f"Revert the scaling and configuration changes from the steps above and redeploy the "
            f"last known-good version of {svc}; no irreversible data changes are involved."
        ),
        references=references,
        requires_human_approval=any(step.requires_approval for step in steps),
    )


def _usage(prompt: str, payload: str) -> TokenUsage:
    # Deterministic estimate (~4 chars/token) so token & cost metrics are stable offline.
    return TokenUsage(
        model="deterministic-offline",
        input_tokens=max(1, len(prompt) // 4),
        output_tokens=max(1, len(payload) // 4),
    )


class DeterministicLLMEngine:
    """A pure, reproducible engine — same incident in, same plan out, on every machine."""

    provider = "deterministic"
    model = "deterministic-offline"

    async def plan(self, incident: IncidentInput, *, feedback: str | None = None) -> PlanResult:
        classification = _classify(incident)
        output = PlanOutput(
            classification=classification, tool_calls=_tool_calls(incident, classification)
        )
        return PlanResult(
            output=output, usage=_usage(planner_user_prompt(incident), output.model_dump_json())
        )

    async def synthesize(
        self,
        incident: IncidentInput,
        classification: IncidentClassification,
        tool_results: list[ToolResult],
        *,
        feedback: str | None = None,
    ) -> SynthResult:
        plan = _synthesize(incident, classification, tool_results)
        prompt = synthesizer_user_prompt(incident, classification, tool_results, feedback=feedback)
        return SynthResult(plan=plan, usage=_usage(prompt, plan.model_dump_json()))

    async def aclose(self) -> None:
        return None
