# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run a registered cloud vision model over a project's untouched tasks under a hard budget.

Rerunning the same action only reaches tasks that still lack a draft from this exact model
version, so completed images are never paid for twice. Before each image the runner stops if the
measured spend plus that image's estimate would pass the action budget; the run record keeps
where it stopped, what it spent, and every call's tokens and cost.
"""

from concurrent.futures import ThreadPoolExecutor
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
from datakeel.prelabel import (
    image_estimate,
    open_client,
    prelabel_prompt,
    prompt_token_estimate,
    resolve_credential,
    run_estimate,
)
from datakeel.storage.production_catalog import require_label_set, require_template
from datakeel.storage.production_catalog_rows import ProductionPrelabelRunRow
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
PRIOR_CALLS = 20
PARALLEL_IMAGES = 4


class CloudTargets(NamedTuple):
    """Tasks still to label, the samples skipped as done or locked, and each sample's size."""

    tasks: list[ProductionTaskRow]
    skipped: list[str]
    sizes: dict[str, tuple[int | None, int | None]]
    prompt_tokens: int
    output_tokens: int | None
    observed_calls: int


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
    output_tokens, observed = observed_output_tokens(session, project, model)
    return CloudTargets(
        eligible,
        [task.sample_id for task in tasks if task.id not in chosen],
        sizes,
        prompt_token_estimate(cloud_prompt(session, project, model)),
        output_tokens,
        observed,
    )


def cloud_prompt(session: Session, project: Project, model: ProductionModel) -> str:
    """Build the exact instruction a run sends for this project's labels and template."""
    if model.cloud is None:
        message = "Cloud prompts need a cloud model"
        raise ValidationError(message)
    kinds, single = cloud_kinds(session, project, model)
    labels = require_label_set(session, project.label_set_id, project.label_set_version).labels
    return prelabel_prompt(
        tuple(label.name for label in labels),
        kinds,
        model.cloud.coordinate_space,
        single_label=single,
    )


def observed_output_tokens(
    session: Session, project: Project, model: ProductionModel
) -> tuple[int | None, int]:
    """Blend measured output lengths with the configured prior, this project's calls first.

    The prior counts as ``PRIOR_CALLS`` pseudo-calls, so a few short replies cannot drag the
    estimate far; calls from other projects are used only when this project has none.
    """
    if model.cloud is None:
        return None, 0
    rows = [
        PrelabelRun.model_validate(row.payload)
        for row in session.scalars(
            select(ProductionPrelabelRunRow).where(
                ProductionPrelabelRunRow.payload["model_id"].as_string() == model.id
            )
        )
    ]
    own = [run for run in rows if run.project_id == project.id]
    lengths = [
        call.output_tokens for run in own or rows for call in run.calls if call.outcome == "ok"
    ]
    if not lengths:
        return None, 0
    prior = model.cloud.expected_output_tokens
    return round((sum(lengths) + PRIOR_CALLS * prior) / (len(lengths) + PRIOR_CALLS)), len(lengths)


def cloud_estimate(model: ProductionModel, targets: CloudTargets) -> PrelabelEstimate:
    """Price only the images this run would actually send."""
    if model.cloud is None:
        message = "Cloud estimates need a cloud model"
        raise ValueError(message)
    sizes = [targets.sizes.get(task.sample_id, (None, None)) for task in targets.tasks]
    return run_estimate(
        model.cloud,
        model.unit_price,
        model.currency,
        sizes,
        already_done=len(targets.skipped),
        prompt_tokens=targets.prompt_tokens,
        output_tokens=targets.output_tokens,
        observed_calls=targets.observed_calls,
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
        self.sent = 0

    def next_image_cost(self) -> Decimal | None:
        """Use this run's measured average per sent image once one has been sent."""
        return self.spent / self.sent if self.sent else None

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
        ledger.sent += 1
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


def _next_cost(
    run: _Run,
    request: CloudRequest,
    targets: CloudTargets,
    ledger: _Ledger,
    task: ProductionTaskRow,
) -> Decimal:
    size = targets.sizes.get(task.sample_id, (None, None))
    return ledger.next_image_cost() or image_estimate(
        request.config, run.model.unit_price, size, targets.output_tokens, targets.prompt_tokens
    )


def _label_all(
    run: _Run, request: CloudRequest, targets: CloudTargets
) -> tuple[_Ledger, PrelabelStop | None]:
    """Send up to four images at a time, admitting each only if the budget still covers it."""
    keys = sample_keys(run.session, run.project)
    ledger = _Ledger()
    budget = Decimal(str(run.params.budget))
    position = 0
    with open_client() as client, ThreadPoolExecutor(PARALLEL_IMAGES) as pool:
        while position < len(targets.tasks):
            batch: list[ProductionTaskRow] = []
            planned = ledger.spent
            for task in targets.tasks[position : position + PARALLEL_IMAGES]:
                next_cost = _next_cost(run, request, targets, ledger, task)
                if planned + next_cost > budget:
                    break
                planned += next_cost
                batch.append(task)
            if not batch:
                task = targets.tasks[position]
                return ledger, PrelabelStop(
                    before_sample_id=task.sample_id,
                    completed_images=position,
                    remaining_images=len(targets.tasks) - position,
                    spent=float(ledger.spent),
                    budget=run.params.budget,
                    next_image_estimate=float(_next_cost(run, request, targets, ledger, task)),
                )

            def send(task: ProductionTaskRow) -> ImageOutcome:
                return label_image(request, task.sample_id, keys.get(task.sample_id), client)

            outcomes = list(pool.map(send, batch))
            for task, outcome in zip(batch, outcomes, strict=True):
                _record(run, ledger, task, outcome)
            position += len(batch)
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
