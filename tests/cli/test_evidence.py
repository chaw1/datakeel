# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Public evidence commands reuse source data, report cache work, and rebuild facts."""

from __future__ import annotations

import argparse
import importlib
import json
from io import StringIO
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from rich.console import Console

from datakeel.core.errors import ExecutionError
from datakeel.sample_evidence import generate_samples
from datakeel.storage.dataset_service import list_datasets
from datakeel.storage.evidence_projection import projection_hash
from datakeel.storage.evidence_store import record_extraction
from tests.evidence.helpers import extraction_event

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database
    from tests.cli.conftest import Invoke

demo_module = importlib.import_module("datakeel.cli.demo")
evidence_module = importlib.import_module("datakeel.cli.evidence")


def test_demo_with_evidence_reuses_sources_and_reports_complete_second_run_cache(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise both real worker passes through the default demonstration command."""
    source = tmp_path / "original.txt"
    source.write_text("Generated original scenario observation.")
    output = StringIO()
    monkeypatch.setattr(demo_module, "Database", lambda: db)
    monkeypatch.setattr(demo_module, "console", Console(file=output, highlight=False))
    monkeypatch.setattr(demo_module, "generate_samples", lambda _directory: [source])
    monkeypatch.setattr(
        evidence_module,
        "generate_samples",
        lambda directory, **_kwargs: generate_samples(directory, 20),
    )
    demo_module.demo(argparse.Namespace(once=True, legacy_only=False))
    first = json.loads(output.getvalue())
    output.seek(0)
    output.truncate()
    demo_module.demo(argparse.Namespace(once=True, legacy_only=False))
    second = json.loads(output.getvalue())
    assert len(list_datasets(db)) == 5
    assert first["dataset_id"] == second["dataset_id"]
    assert first["evidence"]["dataset_id"] == second["evidence"]["dataset_id"]
    assert (
        first["enterprise_documents"]["dataset_id"] == second["enterprise_documents"]["dataset_id"]
    )
    documents = next(
        item
        for item in list_datasets(db)
        if item.id == second["enterprise_documents"]["dataset_id"]
    )
    assert documents.file_count == 6
    assert first["evidence"]["inputs"] == 100
    assert first["evidence"]["extracted"] == 100
    assert second["evidence"]["skipped_cached"] == 100
    assert second["evidence"]["extracted"] == 0
    assert {run["dataset_id"] for run in first["knowledge_graph"]} == {
        run["dataset_id"] for run in second["knowledge_graph"]
    }
    assert all(run["report"]["cached"] > 0 for run in second["knowledge_graph"])


def test_rebuild_command_when_projection_exists_reports_identical_hash(
    db: Database, invoke: Invoke, capsys: pytest.CaptureFixture[str]
) -> None:
    """Replay an actual artifact through the public CLI and retain its canonical identity."""
    record_extraction(db, extraction_event())
    expected = projection_hash(db)
    invoke("rebuild-evidence", "--expected-hash", expected)
    result = json.loads(capsys.readouterr().out)
    assert result["before_hash"] == result["after_hash"] == expected
    assert result["matches"] is True
    assert result["assertions"] == 1


def test_rebuild_command_when_expected_hash_wrong_reports_failure(
    invoke: Invoke, capsys: pytest.CaptureFixture[str]
) -> None:
    """Make an integrity mismatch visible to scripts rather than silently succeeding."""
    with pytest.raises(SystemExit, match="1"):
        invoke("rebuild-evidence", "--expected-hash", "f" * 64)
    assert json.loads(capsys.readouterr().out)["matches"] is False


def test_demo_startup_waits_for_evidence_even_after_legacy_task_completes(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Do not announce a ready evidence demonstration while extraction is pending."""
    timestamps = iter([0, 61])
    checked: list[str] = []

    def complete(_db: Database, task_id: str) -> bool:
        """Keep only the new evidence work pending."""
        checked.append(task_id)
        return task_id == "legacy"

    monkeypatch.setattr(demo_module, "_check_task", complete)
    monkeypatch.setattr(
        demo_module,
        "time",
        SimpleNamespace(monotonic=lambda: next(timestamps), sleep=lambda _seconds: None),
    )
    with pytest.raises(ExecutionError, match="within 60 seconds"):
        demo_module._wait_ready(  # noqa: SLF001  # Test supervision without child processes.
            db, "legacy", "http://127.0.0.1", [], 0, "evidence"
        )
    assert checked == ["legacy", "evidence"]
