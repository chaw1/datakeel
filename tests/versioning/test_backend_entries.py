# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep SQLite maintenance restrictions separate from existing PostgreSQL services."""

from __future__ import annotations

import importlib
import sys
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import inspect

from datakeel import cli
from datakeel.api.app import create_app
from datakeel.persistence.canonical import canonical_schema
from datakeel.persistence.legacy import schema_contributions
from datakeel.storage.database import Database
from datakeel.versioning.models import DatabaseStatus

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.schema import CanonicalSchema, SchemaContribution


@pytest.mark.parametrize("entry", ["worker", "cli", "workflow", "mcp"])
def test_postgres_entries_do_not_call_sqlite_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entry: str
) -> None:
    """Offline dispatch routes CLI initialization to W3 without calling SQLite admission."""
    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path / "home"))
    database = Database("postgresql+pg8000://localhost/unused")
    module = importlib.import_module(
        {
            "worker": "datakeel.worker.runner",
            "cli": "datakeel.cli",
            "workflow": "datakeel.cli.workflow",
            "mcp": "datakeel.mcp.server",
        }[entry]
    )

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("PG service entry must not use SQLite admission or implicitly initialize")

    def reached(*_args: object, **_kwargs: object) -> None:
        msg = "service reached"
        raise StopIteration(msg)

    monkeypatch.setattr(module, "require_current", forbidden)
    monkeypatch.setattr(Database, "migrate", forbidden)
    migrations: list[tuple[tuple[SchemaContribution, ...], CanonicalSchema]] = []

    def migrate(
        contributions: tuple[SchemaContribution, ...], *, canonical: CanonicalSchema
    ) -> None:
        migrations.append((contributions, canonical))

    if entry == "cli":
        monkeypatch.setattr(database, "migrate", migrate)
    monkeypatch.setattr(database.engine, "connect", forbidden)
    monkeypatch.setattr(module, "Database", lambda: database, raising=False)
    monkeypatch.setattr(cli, "load_config", lambda: None)
    try:
        if entry == "mcp":
            assert module.create_server(database).name == "Datakeel"
        else:
            if entry == "worker":
                monkeypatch.setattr(module, "schedule_due", reached)
                invoke = lambda: module.run_worker(database, once=True)  # noqa: E731
            elif entry == "cli":
                monkeypatch.setattr(cli, "_database_command", reached)
                monkeypatch.setattr(sys, "argv", ["datakeel", "export", "--format", "openlineage"])
                invoke = cli.main
            else:
                monkeypatch.setattr(module, "recover_runs", reached)
                args = cli.parser().parse_args(["workflow", "run", "dataset-health"])
                invoke = lambda: module.dispatch(args)  # noqa: E731
            with pytest.raises(StopIteration, match="service reached"):
                invoke()
        assert migrations == (
            [(schema_contributions(), canonical_schema())] if entry == "cli" else []
        )
    finally:
        database.engine.dispose()


def test_default_app_can_restart_with_existing_facts(db: Database) -> None:
    """Real fixtures exercise default startup twice, including PostgreSQL W3 idempotence."""
    before = inspect(db.engine).get_table_names()
    assert create_app(db).state.db is db
    assert create_app(db).state.db is db
    assert inspect(db.engine).get_table_names() == before


@pytest.mark.parametrize("command", [["db", "status"], ["db", "upgrade"], ["migrate"]])
def test_postgres_maintenance_still_refused_before_database_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: list[str],
) -> None:
    """Service compatibility must not enable versioned PG campaigns or backend probing."""
    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path / "absent"))
    monkeypatch.setenv("DATAKEEL_DATABASE_URL", "postgresql://localhost/unused")
    monkeypatch.setattr(sys, "argv", ["datakeel", *command])

    def forbidden() -> None:
        pytest.fail("Maintenance rejection must precede Database construction")

    monkeypatch.setattr(cli, "Database", forbidden)
    with pytest.raises(SystemExit) as result:
        cli.main()
    output = capsys.readouterr()
    report = DatabaseStatus.model_validate_json(output.out)
    assert result.value.code == report.exit_code == 3
    assert report.error
    assert "local SQLite file" in report.error
    assert output.err == ""
    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize("command", [["db", "upgrade"], ["migrate"]])
def test_s3_upgrade_still_refused_without_initializing_local_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: list[str],
) -> None:
    """S3 backup limitations remain explicit and never probe remote object storage."""
    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path / "absent"))
    monkeypatch.delenv("DATAKEEL_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATAKEEL_S3_BUCKET", "generated-fixture")
    monkeypatch.setattr(sys, "argv", ["datakeel", *command])
    with pytest.raises(SystemExit) as result:
        cli.main()
    output = capsys.readouterr()
    report = DatabaseStatus.model_validate_json(output.out)
    assert result.value.code == report.exit_code == 4
    assert report.error
    assert "S3 recovery is outside SQLite scope" in report.error
    assert output.err == ""
    assert not (tmp_path / "absent" / "datakeel.db").exists()
    assert not (tmp_path / "absent" / "backups").exists()
