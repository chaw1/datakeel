# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Minimal maintenance location settings, independent of model/worker configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine, make_url

from datakeel.core.errors import ValidationError


class MaintenanceLocation(BaseSettings):
    """Resolve status paths without parsing unrelated application settings or creating a home."""

    model_config = SettingsConfigDict(env_prefix="DATAKEEL_", extra="forbid", frozen=True)

    home: Path = Path(".datakeel")
    database_url: str | None = None

    def path(self) -> Path:
        """Reject non-file or non-SQLite locations before opening any backend connection."""
        return sqlite_path(self.database_url or f"sqlite:///{self.home.resolve() / 'datakeel.db'}")


def sqlite_path(url: str | URL) -> Path:
    """Resolve a local database filename without probing its existence or creating files."""
    parsed = make_url(url)
    if (
        parsed.get_backend_name() != "sqlite"
        or not parsed.database
        or parsed.database == ":memory:"
    ):
        msg = "Versioned migrations require a local SQLite file (S2)"
        raise ValidationError(msg)
    if parsed.query:
        msg = "SQLite URL options are not supported by versioned migrations"
        raise ValidationError(msg)
    return Path(parsed.database).resolve()


def readonly_engine(path: Path) -> Engine:
    """Percent-encode URI filenames, preserving mode=ro even for special path characters."""
    return create_engine(
        URL.create("sqlite", database=path.resolve().as_uri(), query={"mode": "ro", "uri": "true"})
    )
