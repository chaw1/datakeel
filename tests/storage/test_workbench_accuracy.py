# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Prelabel exact-match rates require approved human references and actual model provenance."""

from pathlib import Path

import pytest

from datakeel.actions.production_parameters import SaveRevisionParams
from datakeel.api.app import create_app
from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.errors import ValidationError
from datakeel.core.production_models import ProductionTask
from datakeel.storage.database import Database
from datakeel.storage.production_queries import get_task
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_statistics import production_prelabel_accuracy
from datakeel.storage.production_tasks import require_task, transition_task
from tests.asgi_client import TestClient
from tests.workbench_helpers import annotation_for, run_action, seed_workbench


def _model(db: Database, task: ProductionTask, annotation: AnnotationRecord) -> str:
    with db.session() as session:
        revision = append_revision(
            session,
            require_task(session, task.id),
            SaveRevisionParams(
                request_id="model-accuracy",
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


def test_prelabel_accuracy_requires_approved_human_reference_and_model_history(
    db: Database, tmp_path: Path
) -> None:
    """Model-only approvals, human-only work and unsubmitted human drafts do not invent accuracy.

    An annotator can no longer submit a model head as it is; a model-only approval still arises
    when a reviewer approves a high-confidence pass-through, which the fixture writes directly.
    """
    project, tasks = seed_workbench(db, tmp_path / "unknown")
    empty = production_prelabel_accuracy(db, project.id)
    assert empty.assessed_tasks == 0
    assert empty.exact_match_rate is None
    head = _model(db, tasks[0], annotation_for("box", tasks[0].sample_id))
    head = _model(db, tasks[0], annotation_for("box", tasks[0].sample_id))
    with pytest.raises(ValidationError, match="Save it as your own revision first"):
        run_action(db, "submit_task", {"task_id": tasks[0].id})
    with db.session() as session:
        task = require_task(session, tasks[0].id)
        task.approved_revision_id = head
        transition_task(session, task, "approved")
        session.commit()
    run_action(
        db,
        "save_revision",
        {
            "task_id": tasks[1].id,
            "previous_revision_id": None,
            "annotation": annotation_for("box", tasks[1].sample_id).model_dump(mode="json"),
        },
    )
    run_action(db, "submit_task", {"task_id": tasks[1].id})
    assert production_prelabel_accuracy(db, project.id).assessed_tasks == 0
    run_action(db, "reopen_task", {"task_id": tasks[0].id, "reason": "Create human reference"})
    run_action(
        db,
        "save_revision",
        {
            "task_id": tasks[0].id,
            "previous_revision_id": head,
            "annotation": annotation_for("box", tasks[0].sample_id).model_dump(mode="json"),
        },
    )
    assert production_prelabel_accuracy(db, project.id).assessed_tasks == 0
    run_action(db, "submit_task", {"task_id": tasks[0].id})
    assessed = production_prelabel_accuracy(db, project.id)
    assert assessed.assessed_tasks == 1
    assert assessed.exact_match_tasks == 1
    assert assessed.exact_match_rate == 1


def test_prelabel_accuracy_compares_latest_preceding_model_with_exact_approved_properties(
    db: Database, tmp_path: Path
) -> None:
    """Only the closest model ancestor is compared, including shape properties, via shared reads."""
    project, tasks = seed_workbench(db, tmp_path / "measured")
    for index, task in enumerate(tasks):
        annotation = annotation_for("box", task.sample_id)
        head = _model(db, task, annotation)
        if index == 0:
            assert annotation.boxes is not None
            box = annotation.boxes[0].model_copy(update={"attributes": {"occluded": False}})
            head = _model(db, task, annotation.model_copy(update={"boxes": (box,)}))
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
    score = production_prelabel_accuracy(db, project.id)
    assert score.assessed_tasks == 2
    assert score.exact_match_tasks == 1
    assert score.exact_match_rate == 0.5
    with TestClient(create_app(db)) as client:
        response = client.post(
            "/api/production/functions/production_prelabel_accuracy",
            json={"project_id": project.id},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"] == score.model_dump(mode="json")
        workbench = client.get(f"/api/production/projects/{project.id}/workbench")
        assert workbench.json()["prelabel_accuracy"] == score.model_dump(mode="json")
