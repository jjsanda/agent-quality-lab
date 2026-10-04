"""Map a tool result back to an :class:`~aql.domain.remediation.EvidenceRef`.

Used by the ``act`` node (to build the run's evidence trail) and by the synthesizer (to make a
remediation plan cite the telemetry it was grounded in) so the two never drift.
"""

from __future__ import annotations

from typing import Any

from aql.domain.remediation import EvidenceKind, EvidenceRef
from aql.domain.tools_schema import ToolName, ToolResult, ToolStatus

__all__ = ["evidence_ref_from_result"]

_KIND_FOR_TOOL: dict[ToolName, EvidenceKind] = {
    ToolName.SEARCH_LOGS: EvidenceKind.LOG,
    ToolName.QUERY_METRICS: EvidenceKind.METRIC,
    ToolName.READ_RUNBOOK: EvidenceKind.RUNBOOK,
    ToolName.OPEN_TICKET: EvidenceKind.TICKET,
}


def _ref_for(result: ToolResult) -> str:
    data: dict[str, Any] = result.result or {}
    if result.name is ToolName.READ_RUNBOOK:
        return str(data.get("slug") or result.call_id)
    if result.name is ToolName.QUERY_METRICS:
        return str(data.get("metric") or result.call_id)
    if result.name is ToolName.OPEN_TICKET:
        return str(data.get("ticket_id") or result.call_id)
    return f"logs:{result.call_id}"


def evidence_ref_from_result(result: ToolResult) -> EvidenceRef | None:
    """Return an :class:`EvidenceRef` for a successful result, else ``None``.

    Example:
        >>> from aql.domain.tools_schema import ToolResult, ToolName, ToolStatus
        >>> r = ToolResult(call_id="tc-3", name=ToolName.READ_RUNBOOK, status=ToolStatus.OK,
        ...                 result={"slug": "latency-troubleshooting"}, latency_ms=1.0)
        >>> evidence_ref_from_result(r).ref
        'latency-troubleshooting'
    """
    if result.status is not ToolStatus.OK:
        return None
    return EvidenceRef(
        kind=_KIND_FOR_TOOL[result.name], ref=_ref_for(result), tool_call_id=result.call_id
    )
