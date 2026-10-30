# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Import offline model predictions through the immutable revision append path."""

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from datakeel.actions.production_catalog_parameters import (
    ImportPredictionsParams,
    RunPrelabelParams,
)
from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord
from datakeel.core.errors import DatakeelError, ValidationError
from datakeel.core.production_catalog_models import (
    ParsedPrediction,
    PredictionFailure,
    PrelabelRun,
    ProductionModel,
)
from datakeel.core.production_models import Project
from datakeel.core.production_prediction_models import PredictionSample
from datakeel.storage.production_catalog import require_label_set, require_model
from datakeel.storage.production_cloud_prelabel import EDITABLE_STATES, start_cloud_prelabel
from datakeel.storage.production_prediction_parsing import parse_coco, parse_yolo
from datakeel.storage.production_prelabel_runs import (
    new_run,
    prediction_samples,
    prediction_tasks,
    save_run,
)
from datakeel.storage.production_prelabel_writes import human_head_task_ids, write_model_draft
from datakeel.storage.production_tasks import require_mutable_project
from datakeel.storage.production_tiers import project_thresholds

if TYPE_CHECKING:
    from datakeel.core.prelabel_models import TaskTier


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
    run = new_run(project.id, params.package_id, model)
    labels = require_label_set(session, project.label_set_id, project.label_set_version)
    tasks = {
        task.sample_id: task for task in prediction_tasks(session, project.id, params.package_id)
    }
    samples = tuple(sample for sample in prediction_samples(session, project) if sample.id in tasks)
    thresholds = project_thresholds(session, project)
    revision_ids: list[str] = []
    confidences: list[float] = []
    failures: list[PredictionFailure] = []
    tiers: list[TaskTier] = []
    parser = parse_coco if params.format == "coco" else parse_yolo
    for file in params.files:
        parsed = parser(file, labels, params.category_mapping, samples)
        failures.extend(parsed.failures)
        for prediction in parsed.predictions:
            task = tasks[prediction.annotation.sample_id]
            try:
                with session.begin_nested():
                    revision_id, tier = write_model_draft(
                        session,
                        project,
                        task,
                        prediction,
                        model,
                        actor,
                        request_id=params.request_id,
                        thresholds=thresholds,
                    )
                revision_ids.append(revision_id)
                confidences.append(prediction.confidence)
                tiers.append(tier)
            except DatakeelError as exc:
                failures.append(
                    PredictionFailure(
                        filename=prediction.filename,
                        sample_id=task.sample_id,
                        code="revision_rejected",
                        message=str(exc),
                    )
                )
    run = run.model_copy(update={"thresholds": thresholds, "tiers": tuple(tiers)})
    return save_run(session, run, revision_ids, failures, confidences, cost=0)


def _center_box(sample: PredictionSample, label: str, model_name: str) -> ParsedPrediction:
    width, height = sample.width or 100, sample.height or 100
    return ParsedPrediction(
        filename=sample.filename,
        confidence=0.95,
        annotation=AnnotationRecord(
            sample_id=sample.id,
            annotator_id=model_name,
            boxes=(
                AnnotationBox(
                    category=label,
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


def run_prelabel(
    session: Session, params: RunPrelabelParams, actor: str, *, plan_id: str | None = None
) -> PrelabelRun:
    """Start a cloud run, or generate deterministic center boxes locally without any client."""
    project = require_mutable_project(session, params.project_id)
    model = require_model(session, params.model_id)
    if model.provider == "cloud":
        return start_cloud_prelabel(session, params, actor, project, model, plan_id=plan_id)
    if model.provider != "fake" or "box" not in model.capabilities:
        message = "Only fake box models and cloud models can run prelabel"
        raise ValidationError(message)
    return _fake_prelabel(session, params, actor, project, model)


def _fake_prelabel(
    session: Session,
    params: RunPrelabelParams,
    actor: str,
    project: Project,
    model: ProductionModel,
) -> PrelabelRun:
    """Draft a center box on every editable task except those whose head a person saved."""
    thresholds = project_thresholds(session, project)
    tiers: list[TaskTier] = []
    run = new_run(project.id, params.package_id, model)
    label = require_label_set(session, project.label_set_id, project.label_set_version).labels[0]
    samples = {sample.id: sample for sample in prediction_samples(session, project)}
    revision_ids: list[str] = []
    failures: list[PredictionFailure] = []
    confidences: list[float] = []
    tasks = prediction_tasks(session, project.id, params.package_id)
    human = human_head_task_ids(session, [task for task in tasks if task.state in EDITABLE_STATES])
    for task in tasks:
        if task.id in human:
            continue
        sample = samples[task.sample_id]
        prediction = _center_box(sample, label.name, model.name)
        try:
            with session.begin_nested():
                revision_id, tier = write_model_draft(
                    session,
                    project,
                    task,
                    prediction,
                    model,
                    actor,
                    request_id=params.request_id,
                    thresholds=thresholds,
                )
            revision_ids.append(revision_id)
            confidences.append(prediction.confidence)
            tiers.append(tier)
        except DatakeelError as exc:
            failures.append(
                PredictionFailure(
                    filename=sample.filename,
                    sample_id=sample.id,
                    code="revision_rejected",
                    message=str(exc),
                )
            )
    edited = tuple(task.sample_id for task in tasks if task.id in human)
    update = {"thresholds": thresholds, "tiers": tuple(tiers), "human_edited_sample_ids": edited}
    return save_run(
        session,
        run.model_copy(update=update),
        revision_ids,
        failures,
        confidences,
        cost=model.estimate_cost(len(revision_ids)),
    )
