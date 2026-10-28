# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Sandbox dispatch preserves attempt audit and fences custom outputs like built-in nodes."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from datakeel.core.custom_sandbox import (
    SandboxOutput,
    SandboxRequest,
    SandboxResources,
    SandboxResult,
)
from datakeel.core.errors import ExecutionError
from datakeel.core.models import FileItem
from datakeel.pipeline import run_pipeline
from datakeel.storage.custom_store import list_custom_runs
from datakeel.storage.database import EventRow, TaskRow, VersionRow
from datakeel.storage.dataset_service import import_paths, list_files
from datakeel.storage.lineage_service import get_graph
from datakeel.storage.task_queue import DatabaseQueue
from datakeel.worker.runner import execute
from tests.storage.test_custom_store import definition, publish

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database

_IMAGE = "datakeel-sandbox-fixture@sha256:" + "a" * 64


def _result(*, success: bool = True) -> SandboxResult:
    return SandboxResult(
        success=success,
        exit_reason="completed" if success else "memory_limit",
        image_digest=_IMAGE,
        resources=SandboxResources(wall_seconds=0.1, memory_peak_bytes=1024),
        outputs=(SandboxOutput(name="cleaned.txt", content=b"cleaned fixture", metadata={}),)
        if success
        else (),
    )


def test_worker_when_approved_custom_node_runs_preserves_output_and_attribution(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the selected input bytes and bounded JSON enter the sandbox request."""
    version = publish(db)
    source = tmp_path / "generated.txt"
    source.write_text("selected generated fixture")
    dataset = import_paths(db, "custom-fixture", [source])
    queue = DatabaseQueue(db)
    task_id = queue.submit(dataset.id, "custom-success", definition(version.id))
    lease = queue.claim()
    assert lease is not None
    requests: list[SandboxRequest] = []

    def sandbox(request: SandboxRequest) -> SandboxResult:
        requests.append(request)
        return _result()

    monkeypatch.setattr("datakeel.worker.custom_runner.run_sandbox", sandbox)
    assert execute(queue, lease)
    assert requests[0].code_hash == version.code_hash
    assert requests[0].inputs[0].content == b"selected generated fixture"
    assert not requests[0].trusted_local
    runs = list_custom_runs(db, version.code_hash)
    assert len(runs) == 1
    assert runs[0].image_digest == _IMAGE
    assert runs[0].params_digest
    assert runs[0].resources.root["memory_peak_bytes"] == 1024
    with db.session() as session:
        task = session.get(TaskRow, task_id)
        assert task is not None
        assert task.state == "COMPLETED"
        output = session.scalar(select(VersionRow).where(VersionRow.task_id == task_id))
        assert output is not None
        assert list_files(db, dataset.id, output.id)[0].filename == "cleaned.txt"
        events = [row.payload for row in session.scalars(select(EventRow))]
    audit = next(event for event in events if event["source_module"] == "sandbox")
    assert audit["quality"]["custom_operator"]["code_hash"] == version.code_hash
    assert audit["quality"]["custom_operator"]["exit_reason"] == "completed"
    graph = get_graph(db, dataset.id)
    assert runs[0].id in {node.asset_id for node in graph.nodes}
    assert any(edge.target == runs[0].id for edge in graph.edges)


def test_worker_when_sandbox_fails_retains_failure_record_and_no_version(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resource and validation failures retain exact version and image attribution."""
    version = publish(db)
    source = tmp_path / "generated.txt"
    source.write_text("generated fixture")
    dataset = import_paths(db, "custom-failure-fixture", [source])
    queue = DatabaseQueue(db)
    task_id = queue.submit(dataset.id, "custom-failure", definition(version.id))
    lease = queue.claim()
    assert lease is not None

    def sandbox(_request: SandboxRequest) -> SandboxResult:
        return _result(success=False).model_copy(update={"stderr": "untrusted user diagnostic"})

    monkeypatch.setattr("datakeel.worker.custom_runner.run_sandbox", sandbox)
    assert execute(queue, lease)
    record = list_custom_runs(db)[0]
    assert not record.success
    assert record.exit_reason == "memory_limit"
    assert record.output_count == 0
    with db.session() as session:
        task = session.get(TaskRow, task_id)
        assert task is not None
        assert task.state == "FAILED"
        assert "untrusted user diagnostic" not in (task.error or "")
        assert session.scalar(select(VersionRow).where(VersionRow.task_id == task_id)) is None
        events = [row.payload for row in session.scalars(select(EventRow))]
    failure = next(event for event in events if event["source_module"] == "sandbox")
    assert failure["run_state"] == "FAILED"
    assert failure["outputs"] == [
        {
            "asset_type": "custom_operator_run",
            "asset_id": record.id,
            "namespace": "default",
            "version": None,
            "display_name": None,
        }
    ]
    assert failure["quality"]["custom_operator"]["image_digest"] == _IMAGE
    visible = get_graph(db, dataset.id).events
    assert any(event.event_id == failure["event_id"] for event in visible)


def test_worker_when_container_runtime_missing_exposes_controlled_diagnostic(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real facade retains a clear missing-runtime error in the failed task and audit."""
    version = publish(db)
    source = tmp_path / "generated.txt"
    source.write_text("selected generated fixture")
    dataset = import_paths(db, "missing-runtime-fixture", [source])
    queue = DatabaseQueue(db)
    task_id = queue.submit(dataset.id, "missing-runtime", definition(version.id))
    lease = queue.claim()
    assert lease is not None
    monkeypatch.setenv("DATAKEEL_SANDBOX_BACKEND", "container")
    monkeypatch.setattr("datakeel.operators.custom_container.shutil.which", lambda _name: None)
    assert execute(queue, lease)
    runs = list_custom_runs(db, version.code_hash)
    assert len(runs) == 1
    assert not runs[0].success
    assert runs[0].exit_reason == "runtime_error"
    assert runs[0].output_count == 0
    with db.session() as session:
        task = session.get(TaskRow, task_id)
        assert task is not None
        assert task.state == "FAILED"
        assert "Docker-compatible runtime" in (task.error or "")
        assert session.scalar(select(VersionRow).where(VersionRow.task_id == task_id)) is None


def test_pipeline_when_custom_executor_missing_fails_without_importing_source(
    tmp_path: Path,
) -> None:
    """Direct in-process DAG execution cannot run unapproved custom code."""
    with pytest.raises(ExecutionError, match="sandbox worker"):
        run_pipeline(
            [FileItem(path="unused", filename="fixture.txt")],
            tmp_path,
            definition("custom.filter@" + "0" * 64),
        )
