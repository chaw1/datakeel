# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run a registered cloud vision model over a project's untouched tasks under a hard budget.

Rerunning the same action only reaches tasks that still lack a draft from this exact model
version, so completed images are never paid for twice. Before each image the runner stops if the
measured spend plus that image's estimate would pass the action budget; the run record keeps
where it stopped, what it spent, and every call's tokens and cost.
"""

from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.production_catalog_parameters import RunPrelabelParams
from datakeel.core.errors import DatakeelError, ValidationError
from datakeel.core.prelabel_models import (
    ConfidenceThresholds,
    PrelabelCall,
    PrelabelDrop,
    PrelabelEstimate,
    PrelabelStop,
    TaskTier,
)
from datakeel.core.production_catalog_models import (
    PredictionFailure,
    PrelabelRun,
    ProductionModel,
)
from datakeel.core.production_models import Project
from datakeel.prelabel import image_estimate, open_client, resolve_credential, run_estimate
from datakeel.storage.production_catalog import require_label_set, require_template
from datakeel.storage.production_cloud_labeling import (
    FAILURE_MESSAGES,
    CloudRequest,
    ImageOutcome,
    cloud_request,
    label_image,
)
from datakeel.storage.production_prelabel_runs import (
    new_run,
    prediction_samples,
    prediction_tasks,
    save_run,
)
from datakeel.storage.production_prelabel_writes import prelabeled_task_ids, write_model_draft
from datakeel.storage.production_rows import ProductionTaskRow
from datakeel.storage.production_task_images import sample_keys
from datakeel.storage.production_tiers import project_thresholds

EDITABLE_STATES = frozenset({"pending", "in_progress"})
CLOUD_KINDS = frozenset({"box", "classification"})


class CloudTargets(NamedTuple):
    """Tasks still to label, the samples skipped as done or locked, and each sample's size."""

    tasks: list[ProductionTaskRow]
    skipped: list[str]
    sizes: dict[str, tuple[int | None, int | None]]


def cloud_kinds(
    session: Session, project: Project, model: ProductionModel
) -> tuple[frozenset[str], bool]:
    """Return the components both the template enables and the model can fill, and single-select."""
    template = require_template(session, project.template_id) if project.template_id else None
    configured = template.component_config.get("components") if template else None
    if isinstance(configured, list):
        enabled = {value for value in configured if isinstance(value, str)}
    else:
        enabled = {template.annotation_type if template else "box"}
    kinds = frozenset(enabled & set(model.capabilities) & CLOUD_KINDS)
    if not kinds:
        message = "This cloud model cannot fill any component the project's template enables"
        raise ValidationError(message)
    single = template is not None and template.component_config.get("label_mode") == "single"
    return kinds, single


def cloud_targets(
    session: Session,
    project: Project,
    model: ProductionModel,
    package_id: str | None,
    *,
    lock: bool,
) -> CloudTargets:
    """Select editable tasks without a draft from this model version; others are skipped."""
    if lock:
        tasks = prediction_tasks(session, project.id, package_id)
    else:
        statement = select(ProductionTaskRow).where(ProductionTaskRow.project_id == project.id)
        if package_id is not None:
            statement = statement.where(ProductionTaskRow.package_id == package_id)
        tasks = list(session.scalars(statement.order_by(ProductionTaskRow.id)))
    done = prelabeled_task_ids(session, [task.id for task in tasks], model)
    eligible = [task for task in tasks if task.state in EDITABLE_STATES and task.id not in done]
    chosen = {task.id for task in eligible}
    sizes: dict[str, tuple[int | None, int | None]] = {
        sample.id: (
            round(sample.width) if sample.width else None,
            round(sample.height) if sample.height else None,
        )
        for sample in prediction_samples(session, project)
    }
    return CloudTargets(
        eligible, [task.sample_id for task in tasks if task.id not in chosen], sizes
    )


def cloud_estimate(model: ProductionModel, targets: CloudTargets) -> PrelabelEstimate:
    """Price only the images this run would actually send."""
    if model.cloud is None:
        message = "Cloud estimates need a cloud model"
        raise ValueError(message)
    sizes = [targets.sizes.get(task.sample_id, (None, None)) for task in targets.tasks]
    return run_estimate(
        model.cloud, model.unit_price, model.currency, sizes, already_done=len(targets.skipped)
    )


class _Ledger:
    """Accumulate per-image results for one run."""

    def __init__(self) -> None:
        self.spent = Decimal(0)
        self.calls: list[PrelabelCall] = []
        self.drops: list[PrelabelDrop] = []
        self.failures: list[PredictionFailure] = []
        self.revision_ids: list[str] = []
        self.confidences: list[float] = []
        self.tiers: list[TaskTier] = []
        self.completed = 0

    def fail(self, task: ProductionTaskRow, code: str, message: str) -> None:
        self.failures.append(
            PredictionFailure(
                filename=task.sample_id, sample_id=task.sample_id, code=code, message=message
            )
        )


def _request(session: Session, project: Project, model: ProductionModel) -> CloudRequest:
    if model.cloud is None:
        message = "Cloud prelabel needs a cloud model"
        raise ValidationError(message)
    secret = resolve_credential(model.cloud)
    if secret is None:
        message = (
            f"Cloud model credential is not available from {model.cloud.credential_source} "
            f"name {model.cloud.credential_env}"
        )
        raise ValidationError(message)
    kinds, single = cloud_kinds(session, project, model)
    label_set = require_label_set(session, project.label_set_id, project.label_set_version)
    labels = {label.id: label.name for label in label_set.labels}
    return cloud_request(model, kinds, labels, secret.get_secret_value(), single_label=single)


class _Run(NamedTuple):
    session: Session
    params: RunPrelabelParams
    actor: str
    project: Project
    model: ProductionModel
    thresholds: ConfidenceThresholds


def _record(run: _Run, ledger: _Ledger, task: ProductionTaskRow, outcome: ImageOutcome) -> None:
    if outcome.calls:
        ledger.spent += outcome.cost + Decimal(str(run.model.unit_price))
    ledger.calls.extend(outcome.calls)
    ledger.drops.extend(outcome.drops)
    if outcome.prediction is None:
        code = outcome.failure or "invalid_response"
        ledger.fail(task, code, FAILURE_MESSAGES.get(code, "The provider returned an error"))
        return
    try:
        with run.session.begin_nested():
            revision_id, tier = write_model_draft(
                run.session,
                run.project,
                task,
                outcome.prediction,
                run.model,
                run.actor,
                request_id=run.params.request_id,
                thresholds=run.thresholds,
            )
    except DatakeelError as exc:
        ledger.fail(task, "revision_rejected", str(exc))
        return
    ledger.revision_ids.append(revision_id)
    ledger.confidences.append(outcome.prediction.confidence)
    ledger.tiers.append(tier)


def _label_all(
    run: _Run, request: CloudRequest, targets: CloudTargets
) -> tuple[_Ledger, PrelabelStop | None]:
    keys = sample_keys(run.session, run.project)
    ledger = _Ledger()
    budget = Decimal(str(run.params.budget))
    with open_client() as client:
        for position, task in enumerate(targets.tasks):
            size = targets.sizes.get(task.sample_id, (None, None))
            next_cost = image_estimate(request.config, run.model.unit_price, size)
            if ledger.spent + next_cost > budget:
                return ledger, PrelabelStop(
                    before_sample_id=task.sample_id,
                    completed_images=position,
                    remaining_images=len(targets.tasks) - position,
                    spent=float(ledger.spent),
                    budget=run.params.budget,
                    next_image_estimate=float(next_cost),
                )
            outcome = label_image(request, task.sample_id, keys.get(task.sample_id), client)
            _record(run, ledger, task, outcome)
    return ledger, None


def run_cloud_prelabel(
    session: Session,
    params: RunPrelabelParams,
    actor: str,
    project: Project,
    model: ProductionModel,
) -> PrelabelRun:
    """Label each remaining image, stopping before the action budget would be passed."""
    record = new_run(project.id, params.package_id, model)
    request = _request(session, project, model)
    targets = cloud_targets(session, project, model, params.package_id, lock=True)
    thresholds = project_thresholds(session, project)
    run = _Run(session, params, actor, project, model, thresholds)
    ledger, stopped = _label_all(run, request, targets)
    record = record.model_copy(
        update={
            "budget": params.budget,
            "estimate": cloud_estimate(model, targets),
            "input_tokens": sum(call.input_tokens for call in ledger.calls),
            "output_tokens": sum(call.output_tokens for call in ledger.calls),
            "calls": tuple(ledger.calls),
            "dropped": tuple(ledger.drops),
            "skipped_sample_ids": tuple(targets.skipped),
            "stopped": stopped,
            "thresholds": thresholds,
            "tiers": tuple(ledger.tiers),
        }
    )
    return save_run(
        session,
        record,
        ledger.revision_ids,
        ledger.failures,
        ledger.confidences,
        cost=float(ledger.spent),
    )
