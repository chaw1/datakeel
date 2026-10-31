# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""A prelabel run never drafts over, or charges for, a task whose head a person saved."""

from pathlib import Path

import httpx
import pytest

from datakeel.actions.production_catalog_parameters import RunPrelabelParams
from datakeel.actions.production_parameters import SaveRevisionParams
from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord
from datakeel.core.production_catalog_models import PrelabelRun
from datakeel.core.production_models import ProductionTask
from datakeel.prelabel import use_transport
from datakeel.storage.database import Database
from datakeel.storage.production_predictions import run_prelabel
from datakeel.storage.production_queries import list_revisions
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_tasks import require_task
from tests.prelabel_support import (
    CREDENTIAL_ENV,
    FIXTURE_CREDENTIAL,
    FakeVision,
    cloud_model,
    seed_cloud_project,
)
from tests.storage.production_catalog_fixtures import catalog_project
from tests.workbench_helpers import run_action


def _person_draws(db: Database, task: ProductionTask) -> None:
    box = AnnotationBox(category="cat", x1=8, y1=10, x2=40, y2=50)
    record = AnnotationRecord(sample_id=task.sample_id, annotator_id="local", boxes=(box,))
    run_action(db, "assign_tasks", {"task_ids": [task.id], "actor": "local"})
    run_action(
        db,
        "save_revision",
        {
            "task_id": task.id,
            "previous_revision_id": None,
            "annotation": record.model_dump(mode="json"),
        },
    )


def test_cloud_run_skips_and_counts_tasks_a_person_already_saved(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No call, no charge, no estimate for the person's task; its head stays theirs."""
    monkeypatch.setenv(CREDENTIAL_ENV, FIXTURE_CREDENTIAL)
    project, tasks = seed_cloud_project(db, tmp_path / "images", count=3, tier="group")
    run_action(db, "register_model", {"model": cloud_model()})
    _person_draws(db, tasks[0])
    values = {"project_id": project.id, "model_id": "vision", "budget": 100}
    fake = FakeVision()
    with use_transport(httpx.MockTransport(fake)):
        run = PrelabelRun.model_validate(run_action(db, "run_prelabel", values).root)
    assert run.human_edited_sample_ids == (tasks[0].sample_id,)
    assert tasks[0].sample_id not in run.skipped_sample_ids
    assert len(run.revision_ids) == 2
    assert len(fake.requests) == 4  # Two images, two views each.
    assert run.estimate is not None
    assert (run.estimate.images, run.estimate.human_edited) == (2, 1)
    (head,) = list_revisions(db, tasks[0].id)
    assert head.source == "human"
    assert head.annotation.boxes is not None
    assert len(head.annotation.boxes) == 1


def test_fake_run_leaves_a_person_saved_task_alone(db: Database) -> None:
    """The offline model path applies the same rule and reports the task apart."""
    fixture = catalog_project(db)
    first = fixture.tasks[0]
    with db.session() as session:
        task = require_task(session, first.id)
        box = AnnotationBox(category="a", x1=1, y1=2, x2=30, y2=40)
        append_revision(
            session,
            task,
            SaveRevisionParams(
                request_id="person",
                task_id=task.id,
                previous_revision_id=None,
                annotation=AnnotationRecord(
                    sample_id=task.sample_id, annotator_id="local", boxes=(box,)
                ),
            ),
            "local",
        )
        params = RunPrelabelParams(
            request_id="fake", project_id=fixture.project.id, model_id="fake", budget=1
        )
        run = run_prelabel(session, params, "local")
        session.commit()
    assert run.human_edited_sample_ids == (first.sample_id,)
    assert len(run.revision_ids) == len(fixture.tasks) - 1
    assert list_revisions(db, first.id)[-1].source == "human"
