# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Prelabel IoU accuracy is computed on approved human references through the shared reads."""

from pathlib import Path

import pytest

from datakeel.actions.production_parameters import SaveRevisionParams
from datakeel.api.app import create_app
from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.production_models import ProductionTask
from datakeel.storage.database import Database
from datakeel.storage.production_queries import get_task
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_statistics import production_prelabel_accuracy
from datakeel.storage.production_tasks import require_task
from tests.asgi_client import TestClient
from tests.workbench_helpers import annotation_for, run_action, seed_workbench


def _model(db: Database, task: ProductionTask, annotation: AnnotationRecord) -> str:
    with db.session() as session:
        revision = append_revision(
            session,
            require_task(session, task.id),
            SaveRevisionParams(
                request_id="model-iou",
                task_id=task.id,
                previous_revision_id=get_task(db, task.id).latest_revision_id,
                annotation=annotation,
                source="model",
                model_name="fixture",
                model_version="1",
                confidence=0.8,
            ),
            "local",
        )
        session.commit()
    return revision.id


def _approve(db: Database, task: ProductionTask, head: str, annotation: AnnotationRecord) -> None:
    run_action(
        db,
        "save_revision",
        {
            "task_id": task.id,
            "previous_revision_id": head,
            "annotation": annotation.model_dump(mode="json"),
        },
    )
    run_action(db, "submit_task", {"task_id": task.id})


def test_iou_accuracy_counts_geometric_hits_and_reports_attributes_apart(
    db: Database, tmp_path: Path
) -> None:
    """A shifted box that still overlaps at 0.6 hits at 0.5, misses at 0.75; attributes apart."""
    project, tasks = seed_workbench(db, tmp_path / "iou")
    human = annotation_for("box", tasks[0].sample_id)
    assert human.boxes is not None
    moved = human.boxes[0].model_copy(update={"y2": 2 + 48 * 0.6, "attributes": {}})
    head = _model(db, tasks[0], human.model_copy(update={"boxes": (moved,)}))
    _approve(db, tasks[0], head, human)
    second = annotation_for("box", tasks[1].sample_id)
    head = _model(db, tasks[1], second)
    _approve(db, tasks[1], head, second)
    score = production_prelabel_accuracy(db, project.id)
    assert score.exact_match_tasks == 1
    assert (score.iou_50.true_positives, score.iou_50.f1, score.iou_50.all_hit_tasks) == (2, 1, 2)
    assert score.iou_75.true_positives == 1
    assert score.iou_75.precision == pytest.approx(0.5)
    assert score.iou_75.all_hit_rate == pytest.approx(0.5)
    assert (score.attribute_agreement.matched_objects, score.attribute_agreement.rate) == (2, 0.5)
    with TestClient(create_app(db)) as client:
        workbench = client.get(f"/api/production/projects/{project.id}/workbench")
        assert workbench.json()["prelabel_accuracy"]["iou_50"]["f1"] == 1
