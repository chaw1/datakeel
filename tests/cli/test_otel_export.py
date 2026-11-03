# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-only export-traces command dispatch."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from datakeel import cli
from datakeel.core.errors import ExecutionError

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_export_traces_when_empty_dispatches_read_only_before_migrate(
    db: Database, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command constructs no migrated database and prints only the accepted count."""
    options: list[bool] = []

    def database(*, read_only: bool) -> Database:
        options.append(read_only)
        return db

    def migrate() -> None:
        msg = "migrate must not run"
        raise AssertionError(msg)

    monkeypatch.setattr(cli, "Database", database)
    monkeypatch.setattr(cli, "configure_logging", lambda: None)
    monkeypatch.setattr(db, "migrate", migrate)
    monkeypatch.setattr("datakeel.harness.otel.export_traces", lambda *_args: 0)
    monkeypatch.setattr(sys, "argv", ["datakeel", "export-traces"])
    cli.main()
    assert options == [True]
    assert capsys.readouterr().out == "0 spans\n"


def test_export_traces_when_export_fails_prints_no_success_count(
    db: Database, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failed export cannot be followed by a misleading success line."""
    monkeypatch.setattr(cli, "Database", lambda *, read_only: db if read_only else None)
    monkeypatch.setattr(cli, "configure_logging", lambda: None)

    def fail(*_args: object) -> int:
        msg = "export failed"
        raise ExecutionError(msg)

    monkeypatch.setattr("datakeel.harness.otel.export_traces", fail)
    monkeypatch.setattr(sys, "argv", ["datakeel", "export-traces"])
    with pytest.raises(ExecutionError, match="export failed"):
        cli.main()
    assert capsys.readouterr().out == ""


def test_parser_when_export_traces_has_conversation_filter_preserves_id() -> None:
    """The optional filter uses the existing conversation identity."""
    args = cli.parser().parse_args(["export-traces", "--conversation-id", "abc"])
    assert (args.command, args.conversation_id) == ("export-traces", "abc")
