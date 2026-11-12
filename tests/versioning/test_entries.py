# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Entry by database-state matrix, JSON errors and immutable status inspection."""

from __future__ import annotations

import importlib
import json
import sys
from typing import TYPE_CHECKING

import pytest

from datakeel import cli
from datakeel.api.app import create_app
from datakeel.core.errors import ValidationError
from datakeel.core.settings import Settings
from datakeel.mcp import create_server
from datakeel.storage.database import Database
from datakeel.versioning import initialize
from datakeel.versioning.campaign_v3 import status, upgrade
from datakeel.versioning.models import DatabaseStatus
from datakeel.versioning.registry import registry
from datakeel.worker.runner import run_worker
from tests.versioning.test_baselines import legacy

if TYPE_CHECKING:
    from pathlib import Path


STATES = ("missing", "empty", "unversioned", "current", "pending", "ahead", "invalid", "isolated")


def _prepare(path: Path, home: Path, state: str, monkeypatch: pytest.MonkeyPatch) -> Database:
    database = Database(f"sqlite:///{path}")
    versions = registry()
    if state not in {"missing", "empty", "invalid"}:
        legacy(database)
    if state in {"current", "pending", "ahead", "isolated"}:
        assert upgrade(path, Settings(home=home), versions).exit_code == 0
    if state == "empty":
        with database.engine.connect():
            pass
    if state == "invalid":
        path.write_bytes(b"not a database")
    if state == "isolated":
        (home / "recovery-isolation.json").write_text("{}")
    if state == "ahead":
        with database.engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO datakeel_schema_versions SELECT 4,checksum,baseline,minimum_reader,"
                "applied_at,campaign,facts FROM datakeel_schema_versions WHERE version=1"
            )
    if state == "pending":
        fourth = versions[-1].model_copy(
            update={
                "version": 4,
                "source": versions[-1].target.id,
                "forward": lambda _c: None,
                "checksum": "3" * 64,
            }
        )
        monkeypatch.setattr("datakeel.versioning.registry", lambda: (*versions, fourth))
        monkeypatch.setattr("datakeel.cli.database.registry", lambda: (*versions, fourth))
    return database


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("entry", ["api", "worker", "cli", "mcp", "demo", "fixture"])
def test_entry_by_database_state_never_implicitly_upgrades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str, entry: str
) -> None:
    """Exercise real admission paths; only explicit empty initialization can create."""
    home = tmp_path / "home"
    home.mkdir()
    path = home / "datakeel.db"
    monkeypatch.setenv("DATAKEEL_HOME", str(home))
    monkeypatch.setenv("DATAKEEL_DATABASE_URL", f"sqlite:///{path}")
    database = _prepare(path, home, state, monkeypatch)
    monkeypatch.setattr(cli, "load_config", lambda: None)
    monkeypatch.setattr(cli, "Database", lambda: database)
    monkeypatch.setattr(sys, "argv", ["datakeel", "export", "--format", "openlineage"])
    demo = importlib.import_module("datakeel.cli.demo")
    monkeypatch.setattr(demo, "Database", lambda: database)

    # Stop immediately after the real demo initializer; no demo or service is launched.
    def seeded(_database: Database) -> tuple[str, str]:
        msg = "demo initialized"
        raise StopIteration(msg)

    monkeypatch.setattr(demo, "seed_demo", seeded)
    calls = {
        "api": lambda: create_app(database),
        "worker": lambda: run_worker(database, once=True),
        "cli": cli.main,
        "mcp": lambda: create_server(database),
        "demo": lambda: demo.demo(cli.parser().parse_args(["demo", "--once"])),
        "fixture": lambda: initialize(database),
    }
    accepted = state == "current" or (
        entry in {"demo", "fixture"} and state in {"missing", "empty"}
    )
    before = path.read_bytes() if path.exists() else None
    try:
        if not accepted:
            with pytest.raises(ValidationError):
                calls[entry]()
            assert (path.read_bytes() if path.exists() else None) == before
        elif entry == "demo":
            with pytest.raises(StopIteration, match="demo initialized"):
                calls[entry]()
        else:
            calls[entry]()
    finally:
        database.engine.dispose()


@pytest.mark.parametrize("state", STATES)
def test_status_matrix_outputs_one_typed_document_without_changing_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], state: str
) -> None:
    """Status dispatch precedes logging, routing loading, Database construction and migration."""
    home = tmp_path / "home"
    home.mkdir()
    path = home / "datakeel.db"
    monkeypatch.setenv("DATAKEEL_HOME", str(home))
    monkeypatch.setenv("DATAKEEL_DATABASE_URL", f"sqlite:///{path}")
    database = _prepare(path, home, state, monkeypatch)
    database.engine.dispose()

    def forbidden() -> None:
        pytest.fail("W4-status-no-generic-initializer")

    monkeypatch.setattr(cli, "Database", forbidden)
    monkeypatch.setattr(cli, "load_config", forbidden)
    monkeypatch.setattr(cli, "configure_logging", forbidden)
    monkeypatch.setattr(sys, "argv", ["datakeel", "db", "status", "--json"])
    before = path.read_bytes() if path.exists() else None
    with pytest.raises(SystemExit) as result:
        cli.main()
    output = capsys.readouterr()
    report = DatabaseStatus.model_validate_json(output.out)
    assert report.state == state
    assert (
        result.value.code
        == report.exit_code
        == (3 if state == "invalid" else 6 if state in {"ahead", "isolated"} else 0)
    )
    assert output.err == ""
    assert (path.read_bytes() if path.exists() else None) == before


@pytest.mark.parametrize(
    "args",
    [
        ["db", "upgrade", "--to", "0"],
        ["db", "upgrade", "--to", "999"],
        ["db", "downgrade"],
        ["db", "upgrade", "--to", "bad"],
        ["migrate", "--unknown"],
    ],
)
def test_cli_parameter_errors_emit_exact_json_exit_two(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    args: list[str],
) -> None:
    """Unknown targets and malformed argument grammars share the stable error contract."""
    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path / "absent"))
    monkeypatch.delenv("DATAKEEL_DATABASE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["datakeel", *args])
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 2
    assert DatabaseStatus.model_validate_json(capsys.readouterr().out).exit_code == 2
    assert not (tmp_path / "absent").exists()


def test_migrate_alias_and_upgrade_are_identical_and_repeat_does_not_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The compatibility entry uses the same early maintenance dispatcher and schema."""
    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("DATAKEEL_DATABASE_URL", raising=False)
    for command in (["migrate"], ["db", "upgrade"]):
        monkeypatch.setattr(sys, "argv", ["datakeel", *command])
        with pytest.raises(SystemExit) as result:
            cli.main()
        assert result.value.code == 0
        report = json.loads(capsys.readouterr().out)
        assert report["state"] == "current"
        if command == ["db", "upgrade"]:
            assert report["backup_manifest"] is None


def test_status_missing_does_not_create_parent_or_maintenance_files(tmp_path: Path) -> None:
    """Neither the absent database nor its nonexistent parent is initialized by inspection."""
    home = tmp_path / "missing"
    assert status(home / "db", home, registry()).state == "missing"
    assert not home.exists()


def test_status_ignores_invalid_unrelated_application_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An invalid worker/provider option cannot prevent missing-file maintenance inspection."""
    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path / "missing"))
    monkeypatch.delenv("DATAKEEL_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATAKEEL_PROVIDER_TIMEOUT", "not-a-number")
    monkeypatch.setattr(sys, "argv", ["datakeel", "db", "status"])
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 0
    assert DatabaseStatus.model_validate_json(capsys.readouterr().out).state == "missing"
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize(("fault", "code"), [("backup", 4), ("data", 5)])
def test_cli_backup_and_migration_failures_return_json_classification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fault: str,
    code: int,
) -> None:
    """Actual failed recovery input and a failed transactional handler get distinct stable exits."""
    from tests.versioning.helpers import seed_toy, toy_registry  # noqa: PLC0415

    path, home = tmp_path / "db", tmp_path / "home"
    seed_toy(path)
    monkeypatch.setenv("DATAKEEL_HOME", str(home))
    monkeypatch.setenv("DATAKEEL_DATABASE_URL", f"sqlite:///{path}")
    monkeypatch.setattr("datakeel.cli.database.registry", lambda: toy_registry(fault))
    arguments = ["datakeel", "db", "upgrade"]
    if fault == "backup":
        arguments.extend(["--backup-manifest", str(tmp_path / "missing.json")])
    monkeypatch.setattr(sys, "argv", arguments)
    with pytest.raises(SystemExit) as result:
        cli.main()
    report = DatabaseStatus.model_validate_json(capsys.readouterr().out)
    assert result.value.code == report.exit_code == code


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("entry", [["db", "upgrade"], ["migrate"]])
def test_upgrade_and_alias_by_database_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    state: str,
    entry: list[str],
) -> None:
    """Maintenance entries upgrade only supported states and share all exit classifications."""
    home = tmp_path / "home"
    home.mkdir()
    path = home / "datakeel.db"
    monkeypatch.setenv("DATAKEEL_HOME", str(home))
    monkeypatch.setenv("DATAKEEL_DATABASE_URL", f"sqlite:///{path}")
    database = _prepare(path, home, state, monkeypatch)
    before = path.read_bytes() if path.exists() else None
    monkeypatch.setattr(sys, "argv", ["datakeel", *entry])
    try:
        with pytest.raises(SystemExit) as result:
            cli.main()
        report = DatabaseStatus.model_validate_json(capsys.readouterr().out)
        expected = 3 if state == "invalid" else 6 if state in {"ahead", "isolated"} else 0
        assert result.value.code == report.exit_code == expected
        if expected:
            assert (path.read_bytes() if path.exists() else None) == before
        else:
            assert report.state == "current"
            if state == "current":
                assert report.backup_manifest is None
                assert report.applied == ()
    finally:
        database.engine.dispose()
