# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Human edits retain model history while recording the actual authenticated actor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.actions.models import ActionContext, ExecuteRequest
from datakeel.actions.production_parameters import SaveRevisionParams
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.models import JsonDocument
from datakeel.storage.production_queries import list_revisions
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_statistics import production_agreement
from datakeel.storage.production_tasks import require_task
from tests.production_helpers import production_fixture

if TYPE_CHECKING:
    from datakeel.core.production_models import AnnotationRevision, ProductionTask
    from datakeel.storage.database import Database


def _model_revision(db: Database, task: ProductionTask) -> AnnotationRevision:
    with db.session() as session:
        revision = append_revision(
            session,
            require_task(session, task.id),
            SaveRevisionParams(
                request_id="model-prediction",
                task_id=task.id,
                previous_revision_id=None,
                annotation=AnnotationRecord(
                    sample_id=task.sample_id, annotator_id="model:fixture", labels=("cat",)
                ),
                source="model",
                model_name="Fixture",
                model_version="1",
                confidence=0.9,
            ),
            "local",
        )
        session.commit()
        return revision


def test_editing_model_prediction_records_the_real_human_annotator(db: Database) -> None:
    """Editing a copied model record assigns its new annotation identity to the human actor."""
    project, tasks = production_fixture(db, count=1)
    original = _model_revision(db, tasks[0])
    plan = prepare_action(
        db,
        "save_revision",
        JsonDocument(
            {
                "request_id": "human-edit",
                "task_id": tasks[0].id,
                "previous_revision_id": original.id,
                "annotation": original.annotation.model_dump(mode="json"),
            }
        ),
        ActionContext(actor="human-editor"),
    )
    result = execute_plan(
        db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor="human-editor")
    )
    assert result.status == "SUCCEEDED"
    revisions = {revision.id: revision for revision in list_revisions(db, tasks[0].id)}
    assert revisions[original.id] == original
    edited = next(revision for revision in revisions.values() if revision.id != original.id)
    assert edited.source == "human"
    assert edited.actor == edited.annotation.annotator_id == "human-editor"
    assert edited.previous_revision_id == original.id
    agreement = production_agreement(db, project.id)
    assert agreement.annotator_count == 2
    assert {
        name
        for pair in agreement.classification.pairs
        for name in (pair.annotator_a, pair.annotator_b)
    } == {"human-editor", "model:fixture"}
