# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Recover real workflow crashes without duplicate action execution or tool invocation."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import text

from datakeel.actions.models import ApprovalDecision
from datakeel.actions.service import approve_plan, get_plan, list_runs
from datakeel.core.workflow_models import WorkflowEvent
from datakeel.runtime.saver import SQLAlchemySaver
from datakeel.runtime.workflow_service import recover_runs
from datakeel.storage.tool_invocations import list_invocations
from datakeel.storage.workflow_store import get_run
from datakeel.storage.workflow_store import list_runs as list_workflow_runs
from tests.workflows.recovery_process import ProcessRequest
from tests.workflows.test_authorization import pause_cleanup

if TYPE_CHECKING:
    from datakeel.storage.database import Database
    from datakeel.storage.views import DatasetView


def _request(db: Database, dataset_id: str, directory: Path) -> ProcessRequest:
    with db.session() as session:
        schema = (
            None if db.sqlite else session.execute(text("SELECT current_schema()")).scalar_one()
        )
    return ProcessRequest(
        database_url=db.engine.url.render_as_string(hide_password=False),
        schema_name=schema,
        dataset_id=dataset_id,
        phase="pause",
        marker=directory / "workflow-crash.marker",
        result=directory / "workflow-events.jsonl",
    )


def _run(request: ProcessRequest) -> subprocess.CompletedProcess[str]:
    path = request.result.with_suffix(".request.json")
    path.write_text(request.model_dump_json(), encoding="utf-8")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(
            ("DATAKEEL_", "AWS_", "OPENAI_", "ANTHROPIC_", "LANGSMITH_", "LANGCHAIN_")
        )
    }
    environment["DATAKEEL_HOME"] = str(request.result.parent / "home")
    return subprocess.run(  # noqa: S603  # Fixed helper module with generated local fixture input.
        [sys.executable, "-m", "tests.workflows.recovery_process", str(path)],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def _approve(db: Database, request: ProcessRequest) -> ProcessRequest:
    recover_runs(db)
    run = next(item for item in list_workflow_runs(db) if item.workflow_id == "low-quality-cleanup")
    assert run.status == "PAUSED"
    assert run.pending_plan_id is not None
    checkpoint = SQLAlchemySaver(db).get_tuple(
        {"configurable": {"thread_id": f"workflow:{run.id}"}}
    )
    assert checkpoint is not None
    assert checkpoint.pending_writes is not None
    assert any(channel == "__interrupt__" for _, channel, _ in checkpoint.pending_writes)
    plan = get_plan(db, run.pending_plan_id)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    return request.model_copy(update={"run_id": run.id, "plan_id": plan.id})


def _assert_recovered(
    db: Database, request: ProcessRequest, process: subprocess.CompletedProcess[str]
) -> None:
    assert process.returncode == 0, process.stderr
    run = get_run(db, request.run_id)
    assert run.status == "SUCCEEDED"
    actions = [item for item in list_runs(db) if item.plan_id == request.plan_id]
    assert len(actions) == 1
    assert actions[0].status == "SUCCEEDED"
    invocations = list_invocations(db, request.run_id)
    counts = Counter(item.name for item in invocations)
    assert counts["delete_files"] == 1
    assert counts["quarantine_files"] == 1
    assert all(value == 1 for value in counts.values()), counts
    events = [
        WorkflowEvent.model_validate_json(line) for line in request.result.read_text().splitlines()
    ]
    assert events[-1].event == "done"
    assert events[-1].run == run
    step = next(item for item in run.steps if item.id == "delete")
    assert step.output == actions[0].model_dump(mode="json")


def test_workflow_recovers_after_interrupt_commit_process_death(
    db: Database, dataset: DatasetView, tmp_path: Path
) -> None:
    """A new process resumes an approval checkpoint persisted immediately before SIGKILL."""
    request = _request(db, dataset.id, tmp_path)
    killed = _run(request)
    assert killed.returncode == -signal.SIGKILL, killed.stderr
    assert request.marker.read_text() == "pause"
    assert [item.action_type for item in list_runs(db)] == ["quarantine_files"]
    request = _approve(db, request).model_copy(update={"phase": "resume"})
    _assert_recovered(db, request, _run(request))


def test_workflow_recovers_after_action_commit_before_checkpoint(
    db: Database, dataset: DatasetView, tmp_path: Path
) -> None:
    """An execute node replay reuses its committed receipt after a second critical crash window."""
    pause_cleanup(db, dataset.id)
    request = _approve(db, _request(db, dataset.id, tmp_path)).model_copy(
        update={"phase": "resume_commit"}
    )
    killed = _run(request)
    assert killed.returncode == -signal.SIGKILL, killed.stderr
    assert request.marker.read_text() == "resume_commit"
    committed = [item.id for item in list_runs(db) if item.plan_id == request.plan_id]
    assert len(committed) == 1
    request = request.model_copy(update={"phase": "resume"})
    _assert_recovered(db, request, _run(request))
    assert [item.id for item in list_runs(db) if item.plan_id == request.plan_id] == committed
