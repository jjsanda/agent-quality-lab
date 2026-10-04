"""Capture Jaeger + Grafana screenshots from the running stack (via Playwright/Chromium).

Run after `make up` (and a `make demo` / a few traced runs). Writes PNGs to docs/screenshots/.
Best-effort: each capture is independent, and failures are reported rather than fatal.
"""

from __future__ import annotations

import asyncio
import json
import sys
import urllib.request
from pathlib import Path

OUT = Path("docs/screenshots")
JAEGER = "http://localhost:16686"
GRAFANA = "http://localhost:3000"


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:  # localhost only
        return json.loads(response.read().decode())


def _jaeger_trace_url() -> str | None:
    data = _get(f"{JAEGER}/api/traces?service=agent-quality-lab&operation=aql.diagnose&limit=1")
    traces = data.get("data") or []
    return f"{JAEGER}/trace/{traces[0]['traceID']}" if traces else None


def _grafana_dashboard_url() -> str | None:
    results = _get(f"{GRAFANA}/api/search?query=agent-quality-lab")
    return f"{GRAFANA}{results[0]['url']}?kiosk&from=now-15m&to=now" if results else None


async def _capture(page_url: str, out: Path, *, settle_ms: int = 3500) -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-gpu"])
        page = await browser.new_page(viewport={"width": 1600, "height": 900})
        await page.goto(page_url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(settle_ms)
        await page.screenshot(path=str(out), full_page=False)
        await browser.close()


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    targets = [
        ("jaeger-trace.png", _jaeger_trace_url()),
        ("grafana-dashboard.png", _grafana_dashboard_url()),
    ]
    failures = 0
    for name, url in targets:
        if not url:
            print(f"skip {name}: no source URL (is the stack running with data?)")
            failures += 1
            continue
        try:
            await _capture(url, OUT / name)
            print(f"captured {name} <- {url}")
        except Exception as exc:  # best-effort tool: report and continue
            print(f"FAILED {name}: {exc}")
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
