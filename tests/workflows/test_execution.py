# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run the three bundled workflows against real tools, actions, and isolated fact stores."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ApprovalDecision
from datakeel.actions.service import approve_plan, get_plan, list_runs
from datakeel.core.agent_models import ResumeInput
from datakeel.core.errors import ConflictError
from datakeel.core.models import JsonDocument
from datakeel.core.workflow_models import WorkflowStart
from datakeel.harness.enterprise_cases import seed_enterprise_case
from datakeel.runtime.workflow_service import recover_runs, resume_workflow, start_workflow
from datakeel.storage.dataset_service import import_paths, list_files
from datakeel.storage.tool_invocations import list_invocations
from datakeel.storage.workflow_recovery import list_audit
from datakeel.storage.workflow_store import get_run, set_status
from datakeel.workflows.execution import WorkflowHooks
from datakeel.workflows.resolver import lookup
from tests.workflows.conftest import ManualClock, worker_hooks

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import JsonValue

    from datakeel.core.workflow_models import WorkflowRun
    from datakeel.storage.database import Database
    from datakeel.storage.views import DatasetView


def step_output(run: WorkflowRun, identity: str) -> JsonValue:
    """Extract one real step output while asserting successful completion."""
    step = next(step for step in run.steps if step.id == identity)
    assert step.status == "SUCCEEDED", step
    return step.output


def test_dataset_health_runs_worker_quality_report_evidence_and_branch(
    db: Database, dataset: DatasetView
) -> None:
    """Pipeline dispatch alone is insufficient: the injected worker completes the queued task."""
    events = list(
        start_workflow(
            db,
            "dataset-health",
            WorkflowStart(
                inputs=JsonDocument({"dataset_id": dataset.id}), idempotency_key="health"
            ),
            hooks=worker_hooks(db),
        )
    )
    run = events[-1].run
    assert events[-1].event == "done"
    assert run.status == "SUCCEEDED"
    assert lookup(step_output(run, "wait"), "state") == "COMPLETED"
    total = lookup(step_output(run, "quality"), "data.total")
    assert isinstance(total, int | float)
    assert 0 <= total <= 100
    assert isinstance(lookup(step_output(run, "report"), "data.body"), str)
    assert lookup(step_output(run, "evidence"), "data.total") == 0
    result = next(
        step
        for step in run.steps
        if step.id in {"healthy", "review"} and step.status == "SUCCEEDED"
    )
    assert lookup(result.output, "total") == total
    assert get_run(db, run.id) == run
    assert Counter(span.name for span in list_invocations(db, run.id))["run_pipeline"] == 1


def test_metric_change_asks_before_and_after_real_reversible_update(
    db: Database, tmp_path: Path
) -> None:
    """The golden semantic fixture yields the documented before and after monetary rows."""
    seed_enterprise_case(db, tmp_path)
    run = list(start_workflow(db, "metric-change", WorkflowStart(idempotency_key="metric")))[-1].run
    assert run.status == "SUCCEEDED"
    assert lookup(step_output(run, "before"), "data.result.rows") == [[4979475]]
    assert lookup(step_output(run, "after"), "data.result.rows") == [[5255975]]
    assert step_output(run, "comparison") == {
        "before_rows": [[4979475]],
        "after_rows": [[5255975]],
        "rows_equal": False,
        "impact": lookup(step_output(run, "impact"), "data"),
    }
    assert [item.name for item in list_invocations(db, run.id)] == [
        "explain_metric",
        "ask_data",
        "impact_of",
        "update_metric",
        "execute_plan",
        "ask_data",
    ]
    assert [item.status for item in list_runs(db)] == ["SUCCEEDED"]
    assert run.pending_plan_id is None


def test_cleanup_quarantines_exact_selection_and_waits_for_signed_resume(
    db: Database, dataset: DatasetView
) -> None:
    """Only the independent low-quality sample is selected, quarantined, and later deleted."""
    run = list(
        start_workflow(
            db,
            "low-quality-cleanup",
            WorkflowStart(
                inputs=JsonDocument({"dataset_id": dataset.id, "quality_max": 0}),
                idempotency_key="cleanup",
            ),
        )
    )[-1].run
    assert run.status == "PAUSED"
    assert run.pending_plan_id is not None
    plan = get_plan(db, run.pending_plan_id)
    assert plan.session_id == run.id
    assert plan.action_type == "delete_files"
    selected = [item.asset_ref.asset_id for item in plan.manifest.objects]
    assert len(selected) == 1
    assert plan.manifest.objects[0].properties["quarantined"] is True
    assert len(list_files(db, dataset.id)) == 2
    assert [item.action_type for item in list_runs(db)] == ["quarantine_files"]
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    resumed = list(
        resume_workflow(db, run.id, ResumeInput(plan_id=plan.id, idempotency_key="resume"))
    )[-1].run
    assert resumed.status == "SUCCEEDED"
    assert [file.filename for file in list_files(db, dataset.id)] == ["healthy.txt"]
    assert lookup(step_output(resumed, "result"), "file_count") == 1
    total = lookup(step_output(resumed, "quality"), "data.total")
    assert isinstance(total, int | float)
    assert total > 0
    assert Counter(item.name for item in list_invocations(db, run.id))["delete_files"] == 1


def test_start_idempotency_reuses_run_without_tools_and_rejects_changed_input(
    db: Database, dataset: DatasetView
) -> None:
    """A caller key binds the original workflow and payload before any new tool effect."""
    request = WorkflowStart(
        inputs=JsonDocument({"dataset_id": dataset.id, "quality_max": 0}),
        idempotency_key="same-start",
    )
    original = list(start_workflow(db, "low-quality-cleanup", request))[-1].run
    spans = list_invocations(db, original.id)
    replayed = list(start_workflow(db, "low-quality-cleanup", request))[-1].run
    assert replayed == original
    assert list_invocations(db, original.id) == spans
    with pytest.raises(ConflictError):
        list(
            start_workflow(
                db,
                "low-quality-cleanup",
                request.model_copy(
                    update={"inputs": JsonDocument({"dataset_id": dataset.id, "quality_max": 5})}
                ),
            )
        )


def test_wait_timeout_stops_before_quality_and_identifies_missing_worker(
    db: Database, dataset: DatasetView
) -> None:
    """A fake monotonic clock reaches the deadline without spending a minute in the test."""
    clock = ManualClock()
    run = list(
        start_workflow(
            db,
            "dataset-health",
            WorkflowStart(
                inputs=JsonDocument({"dataset_id": dataset.id}), idempotency_key="timeout"
            ),
            hooks=WorkflowHooks(clock=clock.now, sleep=clock.sleep),
        )
    )[-1].run
    assert run.status == "FAILED"
    assert run.error is not None
    assert "worker" in run.error.lower()
    assert "datakeel worker" in run.error
    assert next(step for step in run.steps if step.id == "wait").status == "FAILED"
    assert all(
        item.name not in {"get_quality", "get_report", "query_evidence"}
        for item in list_invocations(db, run.id)
    )


def _fail_pipeline(*_arguments: object, **_keywords: object) -> None:
    msg = "injected task failure"
    raise RuntimeError(msg)


def test_failed_worker_task_stops_without_executing_later_steps(
    db: Database, dataset: DatasetView, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real worker failure stops the workflow without retrying its pipeline step."""
    monkeypatch.setattr("datakeel.worker.runner.run_pipeline", _fail_pipeline)
    run = list(
        start_workflow(
            db,
            "dataset-health",
            WorkflowStart(
                inputs=JsonDocument({"dataset_id": dataset.id}), idempotency_key="worker-failure"
            ),
            hooks=worker_hooks(db),
        )
    )[-1].run
    assert run.status == "FAILED"
    assert run.error is not None
    assert "injected task failure" in run.error
    names = [item.name for item in list_invocations(db, run.id)]
    assert names.count("run_pipeline") == 1
    assert "get_quality" not in names


def test_client_disconnect_marks_active_run_interrupted(db: Database, dataset: DatasetView) -> None:
    """Closing the synchronous event iterator cannot leave an orphaned RUNNING record."""
    events = start_workflow(
        db,
        "dataset-health",
        WorkflowStart(
            inputs=JsonDocument({"dataset_id": dataset.id}), idempotency_key="disconnect"
        ),
        hooks=worker_hooks(db),
    )
    first = next(events)
    events.close()
    run = get_run(db, first.run.id)
    assert run.status == "INTERRUPTED"
    assert run.error


def test_cleanup_with_no_low_quality_files_completes_without_approval(
    db: Database, tmp_path: Path
) -> None:
    """An empty selection does not prepare a meaningless quarantine or delete action."""
    healthy = tmp_path / "healthy-only.txt"
    healthy.write_text("Complete generated content providing healthy deterministic evidence.")
    dataset = import_paths(db, "healthy-workflow-fixture", [healthy])
    run = list(
        start_workflow(
            db,
            "low-quality-cleanup",
            WorkflowStart(
                inputs=JsonDocument({"dataset_id": dataset.id, "quality_max": 0}),
                idempotency_key="nothing-to-clean",
            ),
        )
    )[-1].run
    assert run.status == "SUCCEEDED"
    assert step_output(run, "empty") == {"conclusion": "no_low_quality_files"}
    assert run.pending_plan_id is None
    assert list_runs(db) == []
    assert [item.name for item in list_invocations(db, run.id)] == ["search_files"]


def test_missing_dataset_fails_first_tool_without_running_later_steps(db: Database) -> None:
    """A tool error remains visible at its failed step and does not enter a wait node."""
    run = list(
        start_workflow(
            db,
            "dataset-health",
            WorkflowStart(
                inputs=JsonDocument({"dataset_id": "missing-dataset"}),
                idempotency_key="missing-data",
            ),
        )
    )[-1].run
    assert run.status == "FAILED"
    assert next(step for step in run.steps if step.id == "pipeline").status == "FAILED"
    assert next(step for step in run.steps if step.id == "wait").status == "PENDING"
    assert run.error
    assert [item.name for item in list_invocations(db, run.id)] == ["run_pipeline"]


def test_restart_interrupts_orphaned_running_run_and_preserves_active_owner(
    db: Database, dataset: DatasetView
) -> None:
    """Startup ignores a held writer lock and interrupts an abandoned ordinary run."""
    events = start_workflow(
        db,
        "dataset-health",
        WorkflowStart(inputs=JsonDocument({"dataset_id": dataset.id}), idempotency_key="orphan"),
    )
    first = next(events)
    recover_runs(db)
    assert get_run(db, first.run.id).status == "RUNNING"
    events.close()
    set_status(db, first.run.id, "RUNNING")
    recover_runs(db)
    recovered = get_run(db, first.run.id)
    assert recovered.status == "INTERRUPTED"
    assert recovered.error == "Process restarted before workflow completion"
    assert list_audit(db, recovered.id)[-1].kind == "INTERRUPTED"
