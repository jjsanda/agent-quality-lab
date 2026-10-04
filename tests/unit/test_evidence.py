"""Unit tests for the evidence-ref helper."""

from __future__ import annotations

import pytest

from aql.domain.evidence import evidence_ref_from_result
from aql.domain.remediation import EvidenceKind
from aql.domain.tools_schema import ToolName, ToolResult, ToolStatus


@pytest.mark.parametrize(
    "name,result,expected_kind,expected_ref",
    [
        (
            ToolName.QUERY_METRICS,
            {"metric": "latency_p99_ms"},
            EvidenceKind.METRIC,
            "latency_p99_ms",
        ),
        (ToolName.OPEN_TICKET, {"ticket_id": "TCK-1001"}, EvidenceKind.TICKET, "TCK-1001"),
        (ToolName.SEARCH_LOGS, {"total_matched": 3}, EvidenceKind.LOG, "logs:tc-9"),
    ],
)
def test_evidence_ref_kinds(
    name: ToolName, result: dict[str, object], expected_kind: EvidenceKind, expected_ref: str
) -> None:
    ref = evidence_ref_from_result(
        ToolResult(call_id="tc-9", name=name, status=ToolStatus.OK, result=result, latency_ms=1.0)
    )
    assert ref is not None
    assert ref.kind is expected_kind and ref.ref == expected_ref


def test_failed_result_has_no_evidence() -> None:
    failed = ToolResult(
        call_id="tc-9", name=ToolName.SEARCH_LOGS, status=ToolStatus.ERROR, latency_ms=1.0
    )
    assert evidence_ref_from_result(failed) is None
