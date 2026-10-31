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
from datakeel.core.production_models import AnnotationRevision, PassThrough, Project
from datakeel.storage.production_ai_review import prereview
from datakeel.storage.production_assignments import active_assignment
from datakeel.storage.production_catalog import normalize_annotation, require_complete_attributes
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


def _pass_through(
    session: Session,
    project: Project,
    prediction: ParsedPrediction,
    model: ProductionModel,
    actor: str,
    thresholds: ConfidenceThresholds,
) -> PassThrough | None:
    """Name the model, its confidence and the bar it cleared, or hold a draft missing fields."""
    try:
        require_complete_attributes(
            session, project, normalize_annotation(session, project, prediction.annotation)
        )
    except ValidationError:
        return None
    if thresholds.high is None or thresholds.source == "default":
        return None
    return PassThrough(
        model_id=model.id,
        confidence=prediction.confidence,
        high=thresholds.high,
        low=thresholds.low,
        threshold_source=thresholds.source,
        reviewed_objects=thresholds.objects,
        triggered_by=actor,
    )


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
    """Append the draft, tier it, and route untouched, unheld group/team tasks by that tier.

    A pass-through submission is answered for by the person who triggered the run: they become
    the task's annotator, so team separation keeps them from reviewing it. A task someone holds
    only gets the draft; its state and holder stay as they are.
    """
    confidences = prediction_confidences(prediction)
    tier = task_tier(confidences, thresholds.high, thresholds.low)
    held = active_assignment(session, task.id, "annotation") is not None
    routing = route_tier(project, task, tier, pass_through=thresholds.pass_through, held=held)
    accountable = None
    if routing.routed == "submitted":
        accountable = _pass_through(session, project, prediction, model, actor, thresholds)
        if accountable is None:
            routing = routing.model_copy(update={"routed": "draft"})
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
    revision = append_revision(session, task, params, actor, pass_through=accountable)
    if accountable is not None:
        task.annotator_id = actor
        transition_task(session, task, "submitted")
        prereview(session, project, task, revision)
    return revision.id, routing.model_copy(update={"revision_id": revision.id})


def human_head_task_ids(session: Session, tasks: list[ProductionTaskRow]) -> set[str]:
    """Return tasks whose current head a person saved; a model draft must never bury it."""
    heads = {task.latest_revision_id: task.id for task in tasks if task.latest_revision_id}
    if not heads:
        return set()
    human = session.scalars(
        select(ProductionRevisionRow.id).where(
            ProductionRevisionRow.id.in_(list(heads)), ProductionRevisionRow.source == "human"
        )
    )
    return {heads[identifier] for identifier in human}


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
