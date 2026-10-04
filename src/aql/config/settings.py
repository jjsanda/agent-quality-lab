"""Typed application settings (12-factor, pydantic-settings v2).

Every value has a safe default, so an empty environment runs the fully-offline, deterministic
stack (rule-based engine + in-process fake telemetry). ``AQL_*`` variables configure the app;
the conventional un-prefixed ``ANTHROPIC_API_KEY`` / ``OTEL_*`` names are read via aliases.

Example:
    >>> Settings(_env_file=None).llm_provider
    'deterministic'
"""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from aql.domain.state import Budget

__all__ = ["Settings", "LLMProvider", "Transport"]

LLMProvider = Literal["deterministic", "anthropic"]
Transport = Literal["fake", "http"]


class Settings(BaseSettings):
    """Validated settings loaded from the environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_prefix="AQL_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    env: Literal["local", "prod"] = "local"
    log_level: str = "INFO"
    log_json: bool = True

    # --- LLM engine ---
    llm_provider: LLMProvider = "deterministic"
    anthropic_model: str = "claude-opus-4-8"
    anthropic_max_tokens: int = 4096
    anthropic_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("ANTHROPIC_API_KEY", "AQL_ANTHROPIC_API_KEY")
    )

    # --- Telemetry transport ---
    transport: Transport = "fake"
    telemetry_base_url: str = "http://localhost:8080"
    request_timeout_s: float = 10.0
    data_dir: str = "./data"

    # --- Agent budget ---
    max_tool_steps: int = Field(default=6, ge=1, le=20)
    max_retries: int = Field(default=2, ge=0, le=5)

    # --- Observability ---
    otel_enabled: bool = Field(
        default=False, validation_alias=AliasChoices("OTEL_ENABLED", "AQL_OTEL_ENABLED")
    )
    otel_service_name: str = Field(
        default="agent-quality-lab", validation_alias=AliasChoices("OTEL_SERVICE_NAME")
    )
    otel_exporter_otlp_endpoint: str = Field(
        default="http://localhost:4318",
        validation_alias=AliasChoices("OTEL_EXPORTER_OTLP_ENDPOINT"),
    )

    def budget(self) -> Budget:
        """Build the per-run :class:`Budget` from the configured bounds."""
        return Budget(max_tool_steps=self.max_tool_steps, max_retries=self.max_retries)

    def public_info(self) -> dict[str, object]:
        """Non-secret configuration summary (for the CLI ``info`` command)."""
        model = (
            self.anthropic_model if self.llm_provider == "anthropic" else "deterministic-offline"
        )
        return {
            "llm_provider": self.llm_provider,
            "model": model,
            "transport": self.transport,
            "max_tool_steps": self.max_tool_steps,
            "max_retries": self.max_retries,
            "otel_enabled": self.otel_enabled,
        }
