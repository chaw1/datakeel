# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit schema initialization and service admission; never upgrade on startup."""

from pathlib import Path

from datakeel.core.errors import ValidationError
from datakeel.core.settings import get_settings
from datakeel.storage.database import Database
from datakeel.versioning.campaign import apply_version, status, upgrade
from datakeel.versioning.inspect import inspect_database
from datakeel.versioning.location import MaintenanceLocation, sqlite_path
from datakeel.versioning.lock import require_unisolated
from datakeel.versioning.registry import registry


def database_path(database: Database | None = None) -> Path:
    """Resolve only local file SQLite; other backends remain outside the S2 product path."""
    return sqlite_path(database.engine.url) if database else MaintenanceLocation().path()


def require_current(database: Database) -> None:
    """Reject every non-current state before recovery, queues, tools or model initialization."""
    settings = get_settings()
    if database.sqlite and not database.engine.url.database:
        require_unisolated(settings.home)
        with database.engine.connect() as connection:
            report = inspect_database(connection, registry())
        if report.state != "current":
            msg = "Ephemeral fixture database is not current"
            raise ValidationError(msg)
        return
    path = database_path(database)
    require_unisolated(settings.home, path)
    report = status(path, settings.home, registry())
    if report.state != "current" or report.exit_code:
        msg = f"Database {report.state}: {report.error or 'run datakeel db upgrade first'}"
        raise ValidationError(msg)


def initialize(database: Database) -> None:
    """Explicit demo/fixture initializer: create only a missing/empty store; validate restarts."""
    settings = get_settings()
    if database.sqlite and not database.engine.url.database:
        require_unisolated(settings.home)
        with database.engine.connect() as connection:
            report = inspect_database(connection, registry())
            connection.rollback()
            if report.state == "empty":
                apply_version(connection, registry()[0], "ephemeral-fixture")
            elif report.state != "current":
                msg = "Ephemeral fixture requires an empty database"
                raise ValidationError(msg)
        return
    path = database_path(database)
    report = status(path, settings.home, registry())
    if report.state == "current":
        return
    if report.state not in {"missing", "empty"}:
        msg = f"Database {report.state}; run datakeel db upgrade first"
        raise ValidationError(msg)
    result = upgrade(path, settings, registry())
    if result.exit_code:
        raise ValidationError(result.error or "Database initialization failed")
