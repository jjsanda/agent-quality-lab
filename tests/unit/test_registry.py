"""Unit tests for the tool registry (schema export)."""

from __future__ import annotations

import json
from pathlib import Path

from aql.adapters.tools.registry import export_tool_schemas, tool_json_schemas


def test_tool_json_schemas_are_strict() -> None:
    schemas = tool_json_schemas()
    assert set(schemas) == {"search_logs", "query_metrics", "read_runbook", "open_ticket"}
    for schema in schemas.values():
        assert schema["additionalProperties"] is False


def test_export_writes_one_file_per_tool(tmp_path: Path) -> None:
    written = export_tool_schemas(tmp_path)
    assert {p.name for p in written} == {
        "search_logs.json",
        "query_metrics.json",
        "read_runbook.json",
        "open_ticket.json",
    }
    loaded = json.loads((tmp_path / "open_ticket.json").read_text())
    assert loaded["title"] == "OpenTicketArgs"
