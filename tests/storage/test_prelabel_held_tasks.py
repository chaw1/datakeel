# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A prelabel run never routes a task someone holds; it only adds the draft.

Assigned or claimed work, touched or not, and a rework round returned to its holder keep their
state and holder, and the run counts them as drafts only. Unheld work still passes through.
"""

from pathlib import Path

import httpx
import pytest

from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.production_catalog_models import PrelabelRun
from datakeel.core.production_models import AnnotationRevision, ProductionTask, Project
from datakeel.prelabel import use_transport
from datakeel.storage.database import Database
from datakeel.storage.production_prelabel_reads import prelabel_progress
from datakeel.storage.production_queries import (
    get_task,
    list_assignments,
    list_revisions,
    list_tasks,
)
from tests.prelabel_support import (
    CREDENTIAL_ENV,
    FIXTURE_CREDENTIAL,
    FakeVision,
    cloud_model,
    seed_cloud_project,
)
from tests.workbench_helpers import run_action


@pytest.fixture(autouse=True)
def _credential(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CREDENTIAL_ENV, FIXTURE_CREDENTIAL)


def _holder(db: Database, task_id: str) -> str | None:
    """Return who holds the task's annotation assignment now, if anyone."""
    held = [
        item.actor
        for item in list_assignments(db, task_id)
        if item.active and item.stage == "annotation"
    ]
    return held[0] if held else None


def _head(db: Database, task: ProductionTask) -> AnnotationRevision:
    return next(item for item in list_revisions(db, task.id) if item.id == task.latest_revision_id)


def _held_project(db: Database, tmp_path: Path, tier: str) -> tuple[Project, list[str]]:
    """Four pending tasks with a configured high bar; one assigned and one claimed, untouched."""
    project, _ = seed_cloud_project(db, tmp_path / tier, count=4, tier=tier)
    run_action(db, "configure_project", {"project_id": project.id, "confidence_high": 0.9})
    run_action(db, "register_model", {"model": cloud_model(confidence_source="self")})
    claimed = run_action(
        db, "claim_task", {"project_id": project.id, "stage": "annotation"}, actor="ann-b"
    ).root["id"]
    assert isinstance(claimed, str)
    tasks = [task.id for task in list_tasks(db, project.id)]
    assigned = next(task_id for task_id in tasks if task_id != claimed)
    run_action(db, "assign_tasks", {"task_ids": [assigned], "actor": "ann-a"})
    return project, [assigned, claimed]


@pytest.mark.parametrize("tier", ["group", "team"])
def test_assigned_and_claimed_tasks_only_get_a_draft_while_unheld_ones_pass_through(
    db: Database, tmp_path: Path, tier: str
) -> None:
    """Held work keeps its state and holder with a model head; unheld high work is submitted."""
    project, held = _held_project(db, tmp_path, tier)
    before = {task_id: (get_task(db, task_id).state, _holder(db, task_id)) for task_id in held}
    assert before[held[0]] == ("in_progress", "ann-a")
    assert before[held[1]] == ("in_progress", "ann-b")
    with use_transport(httpx.MockTransport(FakeVision(confidence=0.95))):
        details = run_action(
            db, "run_prelabel", {"project_id": project.id, "model_id": "vision", "budget": 10}
        )
    run = PrelabelRun.model_validate(details.root)
    assert (len(run.revision_ids), run.failures) == (4, ())
    tiers = {item.task_id: item for item in run.tiers}
    for task_id in held:
        task = get_task(db, task_id)
        assert (task.state, _holder(db, task_id)) == before[task_id]
        assert task.annotator_id == before[task_id][1]
        head = _head(db, task)
        assert (head.source, head.pass_through) == ("model", None)
        assert (tiers[task_id].tier, tiers[task_id].routed, tiers[task_id].note) == (
            "high",
            "draft",
            "held",
        )
    for task_id in set(tiers) - set(held):
        task = get_task(db, task_id)
        assert (task.state, task.annotator_id, _holder(db, task_id)) == ("submitted", "local", None)
        head = _head(db, task)
        assert head.pass_through is not None
        assert head.pass_through.triggered_by == "local"
        assert tiers[task_id].routed == "submitted"
    assert run.held_drafts == 2
    (progress,) = prelabel_progress(db, project.id)
    assert progress.held_drafts == 2


def _return_for_rework(db: Database, task: ProductionTask) -> None:
    """ann-a takes the task, submits an empty annotation, and rev-1 sends it back."""
    run_action(db, "assign_tasks", {"task_ids": [task.id], "actor": "ann-a"})
    annotation = AnnotationRecord(
        sample_id=task.sample_id,
        annotator_id="ann-a",
        image_width=96,
        image_height=80,
        boxes=(),
    )
    run_action(
        db,
        "save_revision",
        {
            "task_id": task.id,
            "previous_revision_id": None,
            "annotation": annotation.model_dump(mode="json"),
        },
        actor="ann-a",
    )
    run_action(db, "submit_task", {"task_id": task.id}, actor="ann-a")
    head = get_task(db, task.id).latest_revision_id
    run_action(
        db,
        "review_task",
        {"task_id": task.id, "revision_id": head, "decision": "rework", "issues": ["Empty"]},
        actor="rev-1",
    )


@pytest.mark.parametrize("tier", ["group", "team"])
def test_a_rework_round_back_with_its_holder_is_not_passed_through_by_an_import(
    db: Database, tmp_path: Path, tier: str
) -> None:
    """A returned task is pending again but still held: an imported draft does not submit it."""
    project, tasks = seed_cloud_project(db, tmp_path / tier, count=2, tier=tier)
    run_action(db, "configure_project", {"project_id": project.id, "confidence_high": 0.9})
    run_action(
        db,
        "register_model",
        {"model": {"id": "detector", "name": "Detector", "version": "v1", "provider": "import"}},
    )
    returned, free = tasks
    _return_for_rework(db, returned)
    assert (get_task(db, returned.id).state, _holder(db, returned.id)) == ("pending", "ann-a")
    line = "0 0.5 0.5 0.5 0.5 0.95"
    details = run_action(
        db,
        "import_predictions",
        {
            "project_id": project.id,
            "model_id": "detector",
            "format": "yolo",
            "category_mapping": {"0": "cat"},
            "files": [
                {"filename": "a.txt", "sample_id": returned.sample_id, "content": line},
                {"filename": "b.txt", "sample_id": free.sample_id, "content": line},
            ],
        },
    )
    run = PrelabelRun.model_validate(details.root)
    tiers = {item.task_id: item for item in run.tiers}
    task = get_task(db, returned.id)
    assert (task.state, task.annotator_id, _holder(db, returned.id)) == (
        "pending",
        "ann-a",
        "ann-a",
    )
    assert (_head(db, task).source, _head(db, task).pass_through) == ("model", None)
    assert (tiers[returned.id].routed, tiers[returned.id].note) == ("draft", "held")
    assert get_task(db, free.id).state == "submitted"
    assert tiers[free.id].routed == "submitted"
    assert run.held_drafts == 1
