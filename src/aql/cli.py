"""``aql`` command-line interface: ``aql diagnose <incident.json>`` and ``aql info``."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from aql.config.settings import Settings
from aql.domain.incidents import IncidentInput
from aql.domain.state import AgentState
from aql.factory import build_services, run_diagnosis
from aql.observability.logging import configure_logging

__all__ = ["main"]


def _render(state: AgentState, *, as_json: bool) -> None:
    if as_json:
        print(state.model_dump_json(indent=2))
        return

    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console()
    inc = state.incident
    console.print(
        Panel(
            f"[bold]{inc.id}[/] — {inc.title}\n[dim]{inc.service} · {inc.signal}[/]",
            title="Incident",
            border_style="cyan",
        )
    )
    if state.classification is not None:
        c = state.classification
        console.print(
            f"[bold]Classification:[/] [magenta]{c.severity.value.upper()}[/] · "
            f"{c.category.value} · confidence {c.confidence:.2f}"
        )
        console.print(f"[dim]{c.rationale}[/]")

    if state.tool_results:
        table = Table(title="Tool calls", show_header=True, header_style="bold")
        table.add_column("tool")
        table.add_column("status")
        table.add_column("latency", justify="right")
        for r in state.tool_results:
            status = "[green]ok[/]" if r.status.value == "ok" else f"[yellow]{r.status.value}[/]"
            table.add_row(r.name.value, status, f"{r.latency_ms:.0f}ms")
        console.print(table)

    if state.refusal is not None:
        console.print(
            Panel(
                f"[bold red]REFUSED[/] ([italic]{state.refusal.category}[/])\n{state.refusal.reason}\n"
                f"[dim]escalated ticket: {state.refusal.escalated_ticket_id}[/]",
                title="Outcome",
                border_style="red",
            )
        )
    elif state.remediation is not None:
        p = state.remediation
        steps = "\n".join(
            f"  {s.order}. {s.action}"
            + (" [yellow](needs approval)[/]" if s.requires_approval else "")
            for s in p.steps
        )
        console.print(
            Panel(
                f"[bold]Root cause:[/] {p.root_cause_hypothesis}\n"
                f"[bold]Risk:[/] {p.risk_level.value} · human approval: {p.requires_human_approval}\n"
                f"[bold]Steps:[/]\n{steps}\n"
                f"[bold]Rollback:[/] {p.rollback}\n"
                f"[bold]Evidence:[/] {', '.join(r.ref for r in p.references)}",
                title="Remediation plan (advisory)",
                border_style="green",
            )
        )

    total_in = sum(u.input_tokens for u in state.usages)
    total_out = sum(u.output_tokens for u in state.usages)
    model = state.usages[0].model if state.usages else "n/a"
    console.print(f"[dim]tokens: {total_in} in / {total_out} out · model {model}[/]")


async def _diagnose(path: str, *, as_json: bool) -> int:
    settings = Settings()
    configure_logging(level=settings.log_level, json=settings.log_json)
    incident = IncidentInput.model_validate_json(Path(path).read_text(encoding="utf-8"))
    services = build_services(settings)
    try:
        state = await run_diagnosis(services, incident)
    finally:
        await services.aclose()
    _render(state, as_json=as_json)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``aql`` console script."""
    parser = argparse.ArgumentParser(
        prog="aql", description="agent-quality-lab incident-response agent"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    diagnose = sub.add_parser("diagnose", help="Diagnose an incident from a JSON file")
    diagnose.add_argument("incident", help="path to an incident JSON file")
    diagnose.add_argument("--json", action="store_true", help="emit the full result as JSON")
    sub.add_parser("info", help="Print the effective (non-secret) configuration")

    args = parser.parse_args(argv)
    if args.command == "info":
        print(json.dumps(Settings().public_info(), indent=2))
        return 0
    return asyncio.run(_diagnose(args.incident, as_json=args.json))


if __name__ == "__main__":
    raise SystemExit(main())
