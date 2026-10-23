# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The demo reuses its generated dataset and completes work without a server."""

from __future__ import annotations

import argparse
import importlib
import json
from io import StringIO
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from datakeel.core.errors import ExecutionError
from datakeel.storage.database import Database, TaskRow
from datakeel.storage.dataset_service import list_datasets
from datakeel.storage.task_queries import query_task

if TYPE_CHECKING:
    from pathlib import Path

module = importlib.import_module("datakeel.cli.demo")


@pytest.fixture
def seeded(db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    """Provide the seeded test fixture."""
    source = tmp_path / "generated.txt"
    source.write_text(
        "Generated example with sample@users.noreply.github.com contact.", encoding="utf-8"
    )
    monkeypatch.setattr(module, "generate_samples", lambda _directory: [source])
    return module.seed_demo(db)


def test_seed_demo_when_repeated_reuses_dataset_and_idempotent_task(
    db: Database, seeded: tuple[str, str]
) -> None:
    """Verify seed demo when repeated reuses dataset and idempotent task."""
    assert module.seed_demo(db) == seeded
    assert len(list_datasets(db)) == 1


def test_demo_once_when_local_worker_completes_reports_published_task(
    db: Database, seeded: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify demo once when local worker completes reports published task."""
    output = StringIO()
    monkeypatch.setattr(module, "Database", lambda: db)
    monkeypatch.setattr(module, "console", Console(file=output, highlight=False))
    module.demo(argparse.Namespace(once=True, legacy_only=True))
    assert json.loads(output.getvalue())["task_id"] == seeded[1]
    assert query_task(db, seeded[1]).state == "COMPLETED"


def test_demo_once_when_worker_produces_no_terminal_result_raises(
    db: Database, seeded: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify demo once when worker produces no terminal result raises."""
    monkeypatch.setattr(module, "Database", lambda: db)
    monkeypatch.setattr(module, "run_worker", lambda *_args, **_kwargs: None)
    with pytest.raises(ExecutionError, match="Demo task did not complete"):
        module.demo(argparse.Namespace(once=True, legacy_only=True))
    assert query_task(db, seeded[1]).state == "QUEUED"


def test_demo_once_when_task_failed_surfaces_persisted_error(
    db: Database, seeded: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify demo once when task failed surfaces persisted error."""
    monkeypatch.setattr(module, "Database", lambda: db)
    monkeypatch.setattr(module, "run_worker", lambda *_args, **_kwargs: None)
    with db.session() as session:
        task = session.get(TaskRow, seeded[1])
        assert task is not None
        task.state = "FAILED"
        task.error = "Generated failure evidence"
        session.commit()
    with pytest.raises(ExecutionError, match="Generated failure evidence"):
        module.demo(argparse.Namespace(once=True, legacy_only=True))


def test_demo_when_server_mode_selected_dispatches_supervision(
    db: Database, seeded: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify demo when server mode selected dispatches supervision."""
    calls = []
    monkeypatch.setattr(module, "Database", lambda: db)
    monkeypatch.setattr(module, "_serve", lambda *_args: calls.append(_args[1]))
    module.demo(argparse.Namespace(once=False, host="127.0.0.1", port=8765, legacy_only=True))
    assert calls == [seeded[1]]
