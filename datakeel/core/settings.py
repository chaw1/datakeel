# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validated configuration for every application entry point."""

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read the local process environment without caching mutable test settings."""

    model_config = SettingsConfigDict(env_prefix="DATAKEEL_", extra="forbid", frozen=True)

    home: Path = Path(".datakeel")
    database_url: str | None = None
    test_database_url: str | None = None
    s3_bucket: str | None = None
    s3_endpoint: str | None = None
    llm_url: str | None = None
    base_url: str = "http://127.0.0.1:8765"
    log_level: str = "INFO"
    report_timeout: float = Field(default=2.0, gt=0, le=30)
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    openai_url: str = "https://api.openai.com/v1/chat/completions"
    anthropic_url: str = "https://api.anthropic.com/v1/messages"
    provider_timeout: float = Field(default=30, gt=0, le=120)


def get_settings() -> Settings:
    """Resolve the current process configuration through one typed boundary."""
    return Settings()
