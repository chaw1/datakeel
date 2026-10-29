# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Import offline model predictions through the immutable revision append path."""

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.production_catalog_parameters import (
    ImportPredictionsParams,
    RunPrelabelParams,
)
from datakeel.actions.production_parameters import SaveRevisionParams
from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord
from datakeel.core.errors import DatakeelError, ValidationError
from datakeel.core.models import FileItem, new_id, utcnow
from datakeel.core.production_catalog_models import (
    ParsedPrediction,
    PredictionFailure,
    PrelabelRun,
    ProductionModel,
)
from datakeel.core.production_models import Project
from datakeel.core.production_prediction_models import PredictionSample
from datakeel.storage.annotation_store import require_annotation_version
from datakeel.storage.production_catalog import require_label_set, require_model
from datakeel.storage.production_catalog_rows import ProductionPrelabelRunRow
from datakeel.storage.production_prediction_parsing import parse_coco, parse_yolo
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_rows import ProductionTaskRow
from datakeel.storage.production_tasks import require_mutable_project


def prediction_tasks(
    session: Session,
    project_id: str,
    package_id: str | None = None,
) -> list[ProductionTaskRow]:
    """Select only tasks owned by the exact project and optional package."""
    statement = select(ProductionTaskRow).where(ProductionTaskRow.project_id == project_id)
    if package_id is not None:
        statement = statement.where(ProductionTaskRow.package_id == package_id)
    return list(session.scalars(statement.order_by(ProductionTaskRow.id).with_for_update()))


def _dimension(metadata: dict[str, JsonValue], name: str) -> float | None:
    value = metadata.get(name, metadata.get("image_" + name))
    return (
        float(value)
        if isinstance(value, int | float) and not isinstance(value, bool) and value > 0
        else None
    )


def prediction_samples(session: Session, project: Project) -> tuple[PredictionSample, ...]:
    """Read dimensions from the project's pinned immutable manifest."""
    version = require_annotation_version(session, project.dataset_id, project.version_id)
    files = [FileItem.model_validate(item) for item in version.manifest]
    return tuple(
        PredictionSample(
            id=item.id,
            filename=item.filename,
            width=_dimension(item.metadata, "width"),
            height=_dimension(item.metadata, "height"),
        )
        for item in files
    )


def _write_prediction(
    session: Session,
    task: ProductionTaskRow,
    prediction: ParsedPrediction,
    model: ProductionModel,
    actor: str,
    request_id: str,
) -> str:
    params = SaveRevisionParams(
        request_id=request_id,
        task_id=task.id,
        previous_revision_id=task.latest_revision_id,
        annotation=prediction.annotation.model_copy(update={"annotator_id": model.name}),
        source="model",
        model_name=model.name,
        model_version=model.version,
        confidence=prediction.confidence,
    )
    return append_revision(session, task, params, actor).id


def import_predictions(
    session: Session,
    params: ImportPredictionsParams,
    actor: str,
) -> PrelabelRun:
    """Keep valid files even when other files have unknown categories, invalid boxes or bad JSON."""
    project = require_mutable_project(session, params.project_id)
    model = require_model(session, params.model_id)
    if "box" not in model.capabilities:
        message = "COCO and YOLO import requires a box-capable model"
        raise ValidationError(message)
    run = _new_run(project.id, params.package_id, model)
    labels = require_label_set(session, project.label_set_id, project.label_set_version)
    tasks = {
        task.sample_id: task for task in prediction_tasks(session, project.id, params.package_id)
    }
    samples = tuple(sample for sample in prediction_samples(session, project) if sample.id in tasks)
    revision_ids: list[str] = []
    confidences: list[float] = []
    failures: list[PredictionFailure] = []
    parser = parse_coco if params.format == "coco" else parse_yolo
    for file in params.files:
        parsed = parser(file, labels, params.category_mapping, samples)
        failures.extend(parsed.failures)
        for prediction in parsed.predictions:
            task = tasks[prediction.annotation.sample_id]
            try:
                with session.begin_nested():
                    revision_id = _write_prediction(
                        session,
                        task,
                        prediction,
                        model,
                        actor,
                        params.request_id,
                    )
                revision_ids.append(revision_id)
                confidences.append(prediction.confidence)
            except DatakeelError as exc:
                failures.append(
                    PredictionFailure(
                        filename=prediction.filename,
                        sample_id=task.sample_id,
                        code="revision_rejected",
                        message=str(exc),
                    )
                )
    return _save_run(session, run, revision_ids, failures, confidences, cost=0)


def run_prelabel(session: Session, params: RunPrelabelParams, actor: str) -> PrelabelRun:
    """Generate deterministic center boxes locally without constructing any model client."""
    project = require_mutable_project(session, params.project_id)
    model = require_model(session, params.model_id)
    if model.provider != "fake" or "box" not in model.capabilities:
        message = "Only the offline fake box model can run prelabel in this release"
        raise ValidationError(message)
    run = _new_run(project.id, params.package_id, model)
    label = require_label_set(session, project.label_set_id, project.label_set_version).labels[0]
    samples = {sample.id: sample for sample in prediction_samples(session, project)}
    revision_ids: list[str] = []
    failures: list[PredictionFailure] = []
    confidences: list[float] = []
    tasks = prediction_tasks(session, project.id, params.package_id)
    for task in tasks:
        sample = samples[task.sample_id]
        width, height = sample.width or 100, sample.height or 100
        prediction = ParsedPrediction(
            filename=sample.filename,
            confidence=0.95,
            annotation=AnnotationRecord(
                sample_id=sample.id,
                annotator_id=model.name,
                boxes=(
                    AnnotationBox(
                        category=label.name,
                        x1=width / 4,
                        y1=height / 4,
                        x2=width * 3 / 4,
                        y2=height * 3 / 4,
                    ),
                ),
                image_width=width,
                image_height=height,
            ),
        )
        try:
            with session.begin_nested():
                revision_id = _write_prediction(
                    session, task, prediction, model, actor, params.request_id
                )
            revision_ids.append(revision_id)
            confidences.append(prediction.confidence)
        except DatakeelError as exc:
            failures.append(
                PredictionFailure(
                    filename=sample.filename,
                    sample_id=sample.id,
                    code="revision_rejected",
                    message=str(exc),
                )
            )
    return _save_run(
        session,
        run,
        revision_ids,
        failures,
        confidences,
        cost=model.estimate_cost(len(revision_ids)),
    )


def _new_run(project_id: str, package_id: str | None, model: ProductionModel) -> PrelabelRun:
    return PrelabelRun(
        id=new_id(),
        project_id=project_id,
        package_id=package_id,
        model_id=model.id,
        model_name=model.name,
        model_version=model.version,
        revision_ids=(),
        confidences=(),
        cost=0,
        elapsed_seconds=0,
        created_at=utcnow(),
    )


def _save_run(
    session: Session,
    run: PrelabelRun,
    revision_ids: list[str],
    failures: list[PredictionFailure],
    confidences: list[float],
    *,
    cost: float,
) -> PrelabelRun:
    value = run.model_copy(
        update={
            "revision_ids": tuple(revision_ids),
            "failures": tuple(failures),
            "confidences": tuple(confidences),
            "cost": cost,
            "elapsed_seconds": (utcnow() - run.created_at).total_seconds(),
        }
    )
    session.add(
        ProductionPrelabelRunRow(
            id=value.id, project_id=value.project_id, payload=value.model_dump(mode="json")
        )
    )
    return value
