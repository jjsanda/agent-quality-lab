"""A tiny async JSON-over-HTTP helper with bounded retry/backoff.

Shared by the HTTP telemetry adapter. Transient transport errors and 5xx responses are retried;
4xx responses fail fast. Every failure surfaces as a :class:`~aql.domain.exceptions.ToolError`,
which the executor turns into a non-fatal ``ToolResult(status=error)``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from aql.domain.exceptions import ToolError

__all__ = ["HttpJsonClient"]


class HttpJsonClient:
    """Thin wrapper over ``httpx.AsyncClient`` returning parsed JSON dicts."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float = 10.0,
        max_retries: int = 2,
        backoff_s: float = 0.2,
    ) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout_s)
        self._max_retries = max_retries
        self._backoff_s = backoff_s

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.request(method, path, json=json, params=params)
            except httpx.TransportError as exc:
                last = exc
            else:
                if response.status_code >= 500:
                    last = ToolError(f"server error {response.status_code} from {path}")
                elif response.status_code >= 400:
                    raise ToolError(f"request {path} failed: {response.status_code}")
                else:
                    parsed: dict[str, Any] = response.json()
                    return parsed
            if attempt < self._max_retries:
                await asyncio.sleep(self._backoff_s * (2**attempt))
        raise ToolError(f"request {path} failed after {self._max_retries + 1} attempts: {last}")

    async def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", path, json=payload)

    async def get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        return await self._request("GET", path, params=params)

    async def aclose(self) -> None:
        await self._client.aclose()
