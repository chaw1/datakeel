# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Public command grammar and local dispatch perform their declared operations."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Never

import pytest

from datakeel import cli
from datakeel.core.errors import NotFoundError
from datakeel.storage.dataset_service import import_paths

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database
    from tests.cli.conftest import Invoke


@pytest.mark.parametrize(
    ("arguments", "command"),
    [
        (["migrate"], "migrate"),
        (["worker", "--once", "--queue", "io"], "worker"),
        (["demo", "--once"], "demo"),
        (["api", "--port", "9999"], "api"),
        (["export", "--format", "openlineage"], "export"),
    ],
)
def test_parser_when_valid_command_supplied_selects_expected_command(
    arguments: list[str], command: str
) -> None:
    """Verify parser when valid command supplied selects expected command."""
    assert cli.parser().parse_args(arguments).command == command


def test_parser_when_queue_unknown_rejects_command() -> None:
    """Verify parser when queue unknown rejects command."""
    with pytest.raises(SystemExit, match="2"):
        cli.parser().parse_args(["worker", "--queue", "unknown"])


def test_migrate_command_when_run_announces_current_schema(
    invoke: Invoke, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify migrate command when run announces current schema."""
    invoke("migrate")
    assert "Database schema is current." in capsys.readouterr().out


def test_worker_command_when_no_tasks_exist_exits_after_drain(
    invoke: Invoke, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify worker command when no tasks exist exits after drain."""
    invoke("worker", "--once", "--queue", "io")
    assert capsys.readouterr().out == ""


def test_worker_command_when_interrupted_returns_cleanly(
    invoke: Invoke, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify worker command when interrupted returns cleanly."""

    def interrupted(*_args: object, **_kwargs: object) -> Never:
        """Provide the interrupted test fixture."""
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "run_worker", interrupted)
    invoke("worker", "--once")


def test_api_command_when_dispatched_uses_selected_bind_address(
    invoke: Invoke, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify api command when dispatched uses selected bind address."""
    calls = []
    monkeypatch.setattr(cli, "create_app", lambda: "application")
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: calls.append((app, kwargs)))
    invoke("api", "--host", "127.0.0.1", "--port", "9999")
    assert calls == [("application", {"host": "127.0.0.1", "port": 9999})]


def test_demo_command_when_dispatched_passes_once_flag(
    invoke: Invoke, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify demo command when dispatched passes once flag."""
    calls = []
    monkeypatch.setattr(cli, "demo", lambda arguments: calls.append(arguments.once))
    invoke("demo", "--once")
    assert calls == [True]


def test_export_command_when_event_log_empty_prints_empty_json(
    invoke: Invoke, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify export command when event log empty prints empty json."""
    invoke("export", "--format", "openlineage")
    assert json.loads(capsys.readouterr().out) == []


def test_export_command_when_dataset_exists_writes_croissant_document(
    db: Database, tmp_path: Path, invoke: Invoke
) -> None:
    """Verify export command when dataset exists writes croissant document."""
    source = tmp_path / "sample.txt"
    source.write_text("Generated sample", encoding="utf-8")
    created = import_paths(db, "sample", [source])
    output = tmp_path / "dataset.json"
    invoke("export", "--format", "croissant", "--dataset", created.id, "--output", str(output))
    assert json.loads(output.read_text(encoding="utf-8"))["name"] == "sample"


def test_export_command_when_dataset_omitted_selects_first_dataset(
    db: Database, tmp_path: Path, invoke: Invoke, capsys: pytest.CaptureFixture[str]
) -> None:
    """Verify export command when dataset omitted selects first dataset."""
    source = tmp_path / "sample.txt"
    source.write_text("Generated sample", encoding="utf-8")
    import_paths(db, "first", [source])
    invoke("export", "--format", "croissant")
    assert json.loads(capsys.readouterr().out)["name"] == "first"


def test_export_command_when_no_dataset_exists_raises_actionable_error(invoke: Invoke) -> None:
    """Verify export command when no dataset exists raises actionable error."""
    with pytest.raises(NotFoundError, match="run datakeel demo first"):
        invoke("export", "--format", "croissant")


def test_export_default_base_url_when_missing_slash_has_valid_dataset_link(
    db: Database, tmp_path: Path, invoke: Invoke
) -> None:
    """Verify export default base url when missing slash has valid dataset link."""
    source = tmp_path / "url.txt"
    source.write_text("Generated URL verification", encoding="utf-8")
    created = import_paths(db, "url-check", [source])
    output = tmp_path / "export.json"
    invoke("export", "--format", "croissant", "--dataset", created.id, "--output", str(output))
    assert (
        json.loads(output.read_text())["url"] == f"http://127.0.0.1:8765/api/datasets/{created.id}"
    )
