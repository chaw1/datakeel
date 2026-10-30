# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Write one model draft with per-object confidence, its tier, and the tier's routing."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.production_parameters import SaveRevisionParams
from datakeel.annotation_qa import record_objects, task_tier
from datakeel.core.errors import ValidationError
from datakeel.core.prelabel_models import ConfidenceThresholds, TaskTier
from datakeel.core.production_catalog_models import ParsedPrediction, ProductionModel
from datakeel.core.production_models import AnnotationRevision, Project
from datakeel.storage.production_ai_review import prereview
from datakeel.storage.production_catalog import require_complete_attributes
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_rows import ProductionRevisionRow, ProductionTaskRow
from datakeel.storage.production_tasks import transition_task
from datakeel.storage.production_tiers import route_tier


def prediction_confidences(prediction: ParsedPrediction) -> tuple[float, ...]:
    """Per-object confidence in canonical order; one image-level value covers every object."""
    count = len(record_objects(prediction.annotation))
    if len(prediction.object_confidences) == count:
        return prediction.object_confidences
    return (prediction.confidence,) * count


def _auto_submit(
    session: Session, project: Project, task: ProductionTaskRow, revision: AnnotationRevision
) -> bool:
    try:
        require_complete_attributes(session, project, revision.annotation)
    except ValidationError:
        return False
    transition_task(session, task, "submitted")
    prereview(session, project, task, revision)
    return True


def write_model_draft(  # noqa: PLR0913  # The draft needs its task, model, actor, run and tiers.
    session: Session,
    project: Project,
    task: ProductionTaskRow,
    prediction: ParsedPrediction,
    model: ProductionModel,
    actor: str,
    *,
    request_id: str,
    thresholds: ConfidenceThresholds,
) -> tuple[str, TaskTier]:
    """Append the draft, tier it, and route untouched group/team tasks by that tier."""
    confidences = prediction_confidences(prediction)
    tier = task_tier(confidences, thresholds.high, thresholds.low)
    routing = route_tier(project, task, tier)
    params = SaveRevisionParams(
        request_id=request_id,
        task_id=task.id,
        previous_revision_id=task.latest_revision_id,
        annotation=prediction.annotation.model_copy(update={"annotator_id": model.name}),
        source="model",
        model_name=model.name,
        model_version=model.version,
        confidence=prediction.confidence,
        object_confidences=confidences,
        confidence_tier=tier,
    )
    revision = append_revision(session, task, params, actor)
    if routing.routed == "submitted" and not _auto_submit(session, project, task, revision):
        routing = routing.model_copy(update={"routed": "draft"})
    return revision.id, routing


def prelabeled_task_ids(session: Session, task_ids: list[str], model: ProductionModel) -> set[str]:
    """Return tasks that already hold a draft from this exact model name and version."""
    done: set[str] = set()
    if not task_ids:
        return done
    for row in session.scalars(
        select(ProductionRevisionRow).where(
            ProductionRevisionRow.task_id.in_(task_ids),
            ProductionRevisionRow.source == "model",
        )
    ):
        revision = AnnotationRevision.model_validate(row.payload)
        if (revision.model_name, revision.model_version) == (model.name, model.version):
            done.add(revision.task_id)
    return done
