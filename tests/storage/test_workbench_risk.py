# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reviewer risk derives from exact labelled content and has deterministic ordering."""

from pathlib import Path

import pytest

from datakeel.actions.production_parameters import SaveRevisionParams
from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.production_models import ProductionTask
from datakeel.core.workbench_models import WorkbenchProjectQuery, WorkbenchTaskRisk
from datakeel.storage.database import Database
from datakeel.storage.production_queries import get_task
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_tasks import require_task
from datakeel.storage.workbench_reads import workbench_project
from datakeel.storage.workbench_risk import draft_difference, prelabel_difference, review_order
from tests.workbench_helpers import annotation_for, run_action, seed_workbench


def test_prelabel_difference_keeps_shape_attributes_and_excludes_provenance() -> None:
    """Equal shapes agree across annotators; property edits and geometry edits remain visible."""
    model = AnnotationRecord(
        sample_id="s",
        annotator_id="model",
        boxes=(
            AnnotationBox(category="cat", x1=0, y1=0, x2=3, y2=4, attributes={"visible": True}),
        ),
    )
    human = model.model_copy(update={"annotator_id": "person"})
    assert prelabel_difference(human, model) == 0
    assert model.boxes is not None
    box = model.boxes[0]
    changed = human.model_copy(
        update={"boxes": (box.model_copy(update={"attributes": {"visible": False}}),)}
    )
    assert prelabel_difference(changed, model) == 1
    assert prelabel_difference(human.model_copy(update={"boxes": ()}), model) == 1
    empty = human.model_copy(update={"boxes": ()})
    assert prelabel_difference(empty, empty) == 0
    assert (
        prelabel_difference(human.model_copy(update={"attributes": {"verified": True}}), model) > 0
    )
    missing = AnnotationRecord(sample_id="s", annotator_id="model")
    assert prelabel_difference(missing, missing.model_copy(update={"labels": ()})) == 1
    duplicated = model.model_copy(update={"boxes": (box, box)})
    assert prelabel_difference(human, duplicated) == 0.5


def test_review_order_prioritizes_round_then_confidence_then_difference() -> None:
    """Every risk dimension precedes task identity, with absent confidence sorted last."""
    base = ProductionTask(
        id="a",
        project_id="p",
        package_id="pack",
        sample_id="s",
        state="submitted",
        round=1,
        confidence=0.5,
    )
    tasks = (
        base,
        base.model_copy(update={"id": "b"}),
        base.model_copy(update={"id": "c", "confidence": 0.1}),
        base.model_copy(update={"id": "d", "round": 2, "confidence": None}),
    )
    risks = tuple(
        WorkbenchTaskRisk(task_id=task.id, prelabel_difference=1 if task.id == "b" else 0)
        for task in tasks
    )
    assert tuple(task.id for task in review_order(tasks, risks)) == ("d", "c", "b", "a")


def test_model_risk_survives_human_save_and_review_pagination(db: Database, tmp_path: Path) -> None:
    """A human head retains risk from its latest model draft and review ordering precedes paging."""
    project, tasks = seed_workbench(db, tmp_path / "risk")
    run_action(db, "upgrade_project", {"project_id": project.id, "workflow_tier": "group"})
    for index, task in enumerate(tasks):
        with db.session() as session:
            revision = append_revision(
                session,
                require_task(session, task.id),
                SaveRevisionParams(
                    request_id=f"model-{index}",
                    task_id=task.id,
                    previous_revision_id=None,
                    annotation=annotation_for("box", task.sample_id),
                    source="model",
                    model_name="fixture",
                    model_version="1",
                    confidence=0.2 + index / 2,
                ),
                "local",
            )
            session.commit()
        run_action(db, "assign_tasks", {"task_ids": [task.id], "actor": "local"})
        annotation = annotation_for("box", task.sample_id)
        if index:
            annotation = annotation.model_copy(update={"boxes": ()})
        run_action(
            db,
            "save_revision",
            {
                "task_id": task.id,
                "previous_revision_id": revision.id,
                "annotation": annotation.model_dump(mode="json"),
            },
        )
        run_action(db, "submit_task", {"task_id": task.id})
    assert get_task(db, tasks[0].id).confidence is None
    caller = AccessContext(actor="local", entry="ask", scope="query")
    first = workbench_project(db, project.id, caller, WorkbenchProjectQuery(limit=1, view="review"))
    # P31a D2: the AI pre-review risk leads the review order; emptying a confident draft is risky.
    assert first.tasks[0].id == tasks[1].id
    # FIX1: the queue's difference uses B1 matching, so emptying a one-box draft is 100%.
    assert first.task_risks[0].prelabel_difference == 1
    assert first.task_risks[0].ai_risk is not None
    assert first.task_risks[0].ai_risk > 0
    second = workbench_project(
        db,
        project.id,
        caller,
        WorkbenchProjectQuery(limit=1, cursor=first.next_cursor, view="review"),
    )
    assert second.tasks[0].id == tasks[0].id
    assert second.task_risks[0].model_confidence == 0.2
    assert second.task_risks[0].prelabel_difference == 0
    assert (second.task_risks[0].ai_risk or 0) < first.task_risks[0].ai_risk
    assert second.next_cursor is None


def test_queue_difference_ignores_a_few_pixels_and_counts_unmatched_objects() -> None:
    """The B1 rule: a shifted box still matches; a missing or relabelled one does not."""
    box = AnnotationBox(category="cat", x1=10, y1=10, x2=50, y2=40)
    model = AnnotationRecord(sample_id="s", annotator_id="model", boxes=(box,))
    moved = model.model_copy(
        update={"boxes": (box.model_copy(update={"x1": 11, "x2": 51, "y1": 12, "y2": 42}),)}
    )
    assert draft_difference(moved, model) == 0
    assert prelabel_difference(moved, model) == 1
    other = box.model_copy(update={"category": "dog"})
    assert draft_difference(model.model_copy(update={"boxes": (other,)}), model) == 1
    assert draft_difference(model.model_copy(update={"boxes": (box, other)}), model) == (
        pytest.approx(1 / 3)
    )
    empty = model.model_copy(update={"boxes": ()})
    assert draft_difference(empty, empty) == 0
