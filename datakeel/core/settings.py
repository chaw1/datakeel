# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validated configuration for every application entry point."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from datakeel.core.orchestration import OpenLineageNamespace


class Settings(BaseSettings):
    """Read the local process environment; callers share one instance per environment snapshot."""

    model_config = SettingsConfigDict(env_prefix="DATAKEEL_", extra="forbid", frozen=True)

    home: Path = Path(".datakeel")
    accel: Literal["auto", "off", "required"] = "auto"
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
    openai_base_url: str | None = None
    anthropic_base_url: str | None = None
    openai_url: str = "https://api.openai.com/v1/chat/completions"
    anthropic_url: str = "https://api.anthropic.com/v1/messages"
    provider_timeout: float = Field(default=30, gt=0, le=120)
    dq_webhook_url: str | None = None
    dq_webhook_secret: SecretStr | None = None
    dq_webhook_retry_seconds: float = Field(default=5, gt=0, le=3600)
    dq_webhook_max_attempts: int = Field(default=8, ge=1, le=20)
    model_routing_file: Path | None = None
    upload_max_chunk_bytes: int = Field(default=8 * 1024 * 1024, ge=1, le=64 * 1024 * 1024)
    upload_max_concurrency: int = Field(default=4, ge=1, le=32)
    upload_max_file_bytes: int = Field(default=5 * 1024**3, ge=0, le=1024**4)
    # Releases and selected versions freeze whole manifests. Their plans may request a
    # budget above the ordinary 10,000-object / 10 GiB action default, up to this ceiling.
    release_budget_max_objects: int = Field(default=1_000_000, ge=1)
    release_budget_max_bytes: int = Field(default=1024**4, ge=1)
    openlineage_token: SecretStr | None = None
    openlineage_namespaces: dict[str, OpenLineageNamespace] = Field(default_factory=dict)
    airflow_url: str | None = None
    airflow_token: SecretStr | None = None
    airflow_username: str | None = None
    airflow_password: SecretStr | None = None
    airflow_timeout: float = Field(default=30, gt=0, le=120)
    airflow_run_limit: int = Field(default=10, ge=1, le=100)
    delegation_max_depth: int = Field(default=2, ge=1, le=8)
    delegation_max_parallel: int = Field(default=3, ge=1, le=16)
    sandbox_backend: Literal["container", "subprocess"] = "container"
    sandbox_allow_subprocess: bool = False
    sandbox_image: str = ""
    sandbox_docker_host: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "DATAKEEL_SANDBOX_DOCKER_HOST", "DOCKER_HOST", "sandbox_docker_host"
        ),
    )
    media_threads: int = Field(default=0, ge=0, le=64)
    media_timeout_base_seconds: float = Field(default=300.0, gt=0, le=86400)
    media_timeout_ratio: float = Field(default=2.0, gt=0, le=100)
    media_timeout_max_seconds: float = Field(default=21600.0, gt=0, le=172800)

    def extraction_key(self, environment_name: str | None) -> SecretStr | None:
        """Resolve an explicitly selected extraction credential only when it is needed."""
        value = os.environ.get(environment_name) if environment_name else None
        return SecretStr(value) if value else None


def get_settings() -> Settings:
    """Resolve the current process configuration through one typed boundary."""
    return _settings_for(_environment_snapshot())


def _environment_snapshot() -> tuple[tuple[str, str], ...]:
    """Capture the prefixed variables so a changed environment yields fresh settings."""
    return tuple(
        sorted(
            (key, value)
            for key, value in os.environ.items()
            if key.upper().startswith("DATAKEEL_") or key == "DOCKER_HOST"
        )
    )


@lru_cache(maxsize=8)
def _settings_for(_snapshot: tuple[tuple[str, str], ...]) -> Settings:
    """Build settings once per snapshot; parsing on every call dominated demo runtime."""
    return Settings()
