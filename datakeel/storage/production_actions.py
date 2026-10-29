# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Execute production workflow actions within the existing audit and lineage transaction."""

from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan, OperationResult
from datakeel.actions.production_parameters import (
    AssignTasksParams,
    ClaimTaskParams,
    CreateProjectParams,
    ProductionActionParams,
    ReleaseTaskParams,
    ReopenTaskParams,
    ReviewTaskParams,
    SaveRevisionParams,
    SplitPackagesParams,
    SubmitTaskParams,
    UpgradeProjectParams,
)
from datakeel.core.errors import ValidationError
from datakeel.core.models import AssetRef
from datakeel.core.production_models import AnnotationRevision, ProductionTask, Project, Review
from datakeel.storage.action_store import audit
from datakeel.storage.production_assignments import assign_tasks, claim_task, release_task
from datakeel.storage.production_projects import (
    create_project,
    record_project_member,
    split_packages,
    upgrade_project,
)
from datakeel.storage.production_reviews import reopen_task, review_task, submit_task
from datakeel.storage.production_revisions import append_revision
from datakeel.storage.production_tasks import require_project, require_task


def _result(
    kind: str, value: AnnotationRevision | ProductionTask | Project | Review
) -> OperationResult:
    return OperationResult(
        outputs=[AssetRef(asset_type=kind, asset_id=str(value.id))],
        details=value.model_dump(mode="json"),
    )


def execute_production_action(
    session: Session,
    plan: ActionPlan,
    params: ProductionActionParams,
) -> OperationResult:
    """Apply one typed workflow mutation without opening or committing a second transaction."""
    if isinstance(params, CreateProjectParams):
        return _result("project", create_project(session, params, plan.actor))
    if isinstance(params, SplitPackagesParams):
        packages = split_packages(session, params)
        return OperationResult(
            outputs=[AssetRef(asset_type="task_package", asset_id=item.id) for item in packages],
            details={"packages": [item.model_dump(mode="json") for item in packages]},
        )
    if isinstance(params, AssignTasksParams):
        return _assign(session, params)
    if isinstance(params, ClaimTaskParams):
        suggestion = record_project_member(session, params.project_id, plan.actor)
        result = _result("production_task", claim_task(session, params, plan.actor))
        return _suggest(result, suggestion=suggestion)
    if isinstance(params, ReleaseTaskParams):
        return _result("production_task", release_task(session, params, plan.actor))
    return _editing_action(session, plan, params)


def _editing_action(
    session: Session,
    plan: ActionPlan,
    params: ProductionActionParams,
) -> OperationResult:
    if isinstance(params, SaveRevisionParams):
        return _save(session, plan, params)
    if isinstance(params, SubmitTaskParams):
        task = submit_task(session, params, plan.actor)
        if require_project(session, task.project_id).workflow_tier == "personal":
            audit(
                session,
                plan,
                "SYSTEM_APPROVAL",
                "APPROVED",
                "Personal submission automatically passed",
            )
        return _result("production_task", task)
    if isinstance(params, ReviewTaskParams):
        return _result("review", review_task(session, params, plan.actor))
    if isinstance(params, ReopenTaskParams):
        return _result("production_task", reopen_task(session, params))
    if isinstance(params, UpgradeProjectParams):
        return _result("project", upgrade_project(session, params))
    message = "Unknown production workflow action parameters"
    raise ValidationError(message)


def _save(session: Session, plan: ActionPlan, params: SaveRevisionParams) -> OperationResult:
    if params.source != "human":
        message = "Model revisions must be created by import_predictions or run_prelabel"
        raise ValidationError(message)
    task = require_task(session, params.task_id)
    annotation = params.annotation.model_copy(update={"annotator_id": plan.actor})
    normalized = params.model_copy(update={"annotation": annotation})
    revision = append_revision(session, task, normalized, plan.actor)
    suggestion = record_project_member(session, task.project_id, plan.actor)
    result = _result("annotation_revision", revision)
    return _suggest(result, suggestion=suggestion)


def _assign(session: Session, params: AssignTasksParams) -> OperationResult:
    task = require_task(session, params.task_ids[0])
    suggestion = record_project_member(session, task.project_id, params.actor)
    assignments = assign_tasks(session, params)
    return OperationResult(
        outputs=[AssetRef(asset_type="assignment", asset_id=item.id) for item in assignments],
        details={
            "assignments": [item.model_dump(mode="json") for item in assignments],
            "suggest_review": suggestion,
        },
    )


def _suggest(result: OperationResult, *, suggestion: bool) -> OperationResult:
    return result.model_copy(update={"details": {**result.details, "suggest_review": suggestion}})
