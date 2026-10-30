# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Select, price and start a cloud vision run over a project's untouched tasks.

Rerunning the same action only reaches tasks that still lack a draft from this exact model
version, so completed images are never paid for twice. Starting a run is the short part inside
the action's transaction; ``production_cloud_runner`` makes the calls afterwards.
"""

from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.production_catalog_parameters import RunPrelabelParams
from datakeel.core.errors import ValidationError
from datakeel.core.prelabel_models import PrelabelEstimate
from datakeel.core.production_catalog_models import PrelabelRun, ProductionModel
from datakeel.core.production_models import Project
from datakeel.prelabel import (
    prelabel_prompt,
    prompt_token_estimate,
    resolve_credential,
    run_estimate,
)
from datakeel.storage.production_catalog import require_label_set, require_template
from datakeel.storage.production_catalog_rows import ProductionPrelabelRunRow
from datakeel.storage.production_cloud_labeling import CloudRequest, cloud_request
from datakeel.storage.production_prelabel_runs import (
    claim_run_slot,
    new_run,
    prediction_samples,
    prediction_tasks,
    save_run,
)
from datakeel.storage.production_prelabel_writes import prelabeled_task_ids
from datakeel.storage.production_rows import ProductionTaskRow
from datakeel.storage.production_tiers import project_thresholds

EDITABLE_STATES = frozenset({"pending", "in_progress"})
CLOUD_KINDS = frozenset({"box", "classification"})
PRIOR_CALLS = 20


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


def cloud_request_for(session: Session, project: Project, model: ProductionModel) -> CloudRequest:
    """Check the credential and template, then fix the prompt, labels and secret for a run."""
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


def start_cloud_prelabel(
    session: Session,
    params: RunPrelabelParams,
    actor: str,
    project: Project,
    model: ProductionModel,
    *,
    plan_id: str | None,
) -> PrelabelRun:
    """Claim the project's run slot and freeze targets, estimate and thresholds; call nothing.

    This is the short part inside the action's transaction. The model calls happen after it
    commits, outside any transaction, and each batch of results is written on its own.
    """
    cloud_request_for(session, project, model)
    claim_run_slot(session, project.id)
    targets = cloud_targets(session, project, model, params.package_id, lock=True)
    record = new_run(project.id, params.package_id, model)
    record = record.model_copy(
        update={
            "status": "running",
            "actor": actor,
            "plan_id": plan_id,
            "budget": params.budget,
            "estimate": cloud_estimate(model, targets),
            "skipped_sample_ids": tuple(targets.skipped),
            "thresholds": project_thresholds(session, project),
            "planned_images": len(targets.tasks),
            "updated_at": record.created_at,
        }
    )
    return save_run(session, record, [], [], [], cost=0)
