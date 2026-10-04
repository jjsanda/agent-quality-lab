"""The real Claude engine (live mode), behind the same :class:`LLMEngine` port.

Structured output is obtained with the canonical, version-tolerant pattern: define a single tool
whose ``input_schema`` is the target Pydantic model's JSON schema, force ``tool_choice`` to it,
then validate the returned ``tool_use.input`` with Pydantic on our side. We deliberately omit
``strict: true`` so our richly-constrained schemas (min/max length, patterns) are accepted; the
constraints are still enforced by ``model_validate`` and a failure feeds the graph's retry loop.

The ``anthropic`` SDK is imported lazily, so the offline stack needs neither the SDK nor a key.
Default model ``claude-opus-4-8``; ``claude-sonnet-5`` / ``claude-haiku-4-5`` are selectable.
"""

from __future__ import annotations

from typing import Any

from aql.adapters.llm.base import PlanOutput, PlanResult, SynthResult
from aql.domain.exceptions import ProviderUnavailableError
from aql.domain.incidents import IncidentClassification, IncidentInput
from aql.domain.prompts import (
    PLANNER_SYSTEM,
    SYNTHESIZER_SYSTEM,
    planner_user_prompt,
    synthesizer_user_prompt,
)
from aql.domain.remediation import RemediationPlan
from aql.domain.state import TokenUsage
from aql.domain.tools_schema import ToolResult

__all__ = ["AnthropicLLMEngine", "PLAN_TOOL", "REMEDIATION_TOOL"]

PLAN_TOOL = "submit_incident_plan"
REMEDIATION_TOOL = "submit_remediation_plan"


def _first_tool_input(message: Any, tool_name: str) -> dict[str, Any]:
    for block in message.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
            return dict(block.input)
    raise ProviderUnavailableError(f"model did not return the forced tool {tool_name!r}")


class AnthropicLLMEngine:
    """Calls the Anthropic Messages API for the plan/synthesize stages."""

    provider = "anthropic"

    def __init__(
        self,
        *,
        model: str = "claude-opus-4-8",
        max_tokens: int = 4096,
        timeout_s: float = 60.0,
        client: Any | None = None,
    ) -> None:
        import anthropic  # lazy: the offline stack must not require the SDK

        self._anthropic = anthropic
        self._client = client if client is not None else anthropic.AsyncAnthropic(timeout=timeout_s)
        self.model = model
        self._max_tokens = max_tokens

    async def _structured(
        self,
        *,
        system: str,
        user: str,
        tool_name: str,
        tool_description: str,
        schema: dict[str, Any],
    ) -> tuple[dict[str, Any], TokenUsage]:
        try:
            message = await self._client.messages.create(
                model=self.model,
                max_tokens=self._max_tokens,
                system=system,
                tools=[
                    {"name": tool_name, "description": tool_description, "input_schema": schema}
                ],
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": user}],
            )
        except (
            self._anthropic.AnthropicError
        ) as exc:  # network / API / rate-limit (after SDK retries)
            raise ProviderUnavailableError(f"Anthropic API call failed: {exc}") from exc
        usage = TokenUsage(
            model=self.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )
        return _first_tool_input(message, tool_name), usage

    async def plan(self, incident: IncidentInput, *, feedback: str | None = None) -> PlanResult:
        user = planner_user_prompt(incident)
        if feedback:
            user += f"\n\nYour previous plan was rejected:\n{feedback}\nRe-emit a valid plan."
        payload, usage = await self._structured(
            system=PLANNER_SYSTEM,
            user=user,
            tool_name=PLAN_TOOL,
            tool_description="Submit the incident classification and the read-only tool calls to run.",
            schema=PlanOutput.model_json_schema(),
        )
        return PlanResult(output=PlanOutput.model_validate(payload), usage=usage)

    async def synthesize(
        self,
        incident: IncidentInput,
        classification: IncidentClassification,
        tool_results: list[ToolResult],
        *,
        feedback: str | None = None,
    ) -> SynthResult:
        payload, usage = await self._structured(
            system=SYNTHESIZER_SYSTEM,
            user=synthesizer_user_prompt(incident, classification, tool_results, feedback=feedback),
            tool_name=REMEDIATION_TOOL,
            tool_description="Submit the final advisory remediation plan grounded in the evidence.",
            schema=RemediationPlan.model_json_schema(),
        )
        return SynthResult(plan=RemediationPlan.model_validate(payload), usage=usage)

    async def aclose(self) -> None:
        close = getattr(self._client, "close", None)
        if close is not None:
            await close()
