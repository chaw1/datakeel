# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Freeze exact production targets while leaving next-task selection free to race safely."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.production_parameters import (
    AssignTasksParams,
    ClaimTaskParams,
    ConfigureProjectParams,
    CreateProjectParams,
    ProductionActionParams,
    SaveRevisionParams,
    SplitPackagesParams,
    TaskIdentityParams,
    UpgradeProjectParams,
)
from datakeel.core.models import JsonDocument
from datakeel.storage.object_projection import content_digest
from datakeel.storage.production_rows import (
    ProductionAssignmentRow,
    ProductionPackageRow,
    ProductionProjectRow,
)
from datakeel.storage.production_tasks import require_project, require_task, task_view


def production_state(session: Session, params: ProductionActionParams) -> str:
    """Hash only facts relevant to the plan, preserving concurrent claim and independent saves."""
    if isinstance(params, CreateProjectParams):
        return content_digest(params.model_dump(mode="json"))
    if isinstance(params, ClaimTaskParams):
        project = require_project(session, params.project_id)
        return content_digest(
            {
                "project_id": project.id,
                "workflow_tier": project.workflow_tier,
                "finalized_version_id": project.finalized_version_id,
            }
        )
    if isinstance(params, SplitPackagesParams):
        return content_digest(
            [
                row.payload
                for row in session.scalars(
                    select(ProductionPackageRow)
                    .where(ProductionPackageRow.project_id == params.project_id)
                    .order_by(ProductionPackageRow.id)
                )
            ]
        )
    if isinstance(params, SaveRevisionParams):
        task = require_task(session, params.task_id)
        project = require_project(session, task.project_id)
        return content_digest(
            {
                "task_id": task.id,
                "workflow_tier": project.workflow_tier,
                "finalized_version_id": project.finalized_version_id,
            }
        )
    if isinstance(params, UpgradeProjectParams | ConfigureProjectParams):
        return content_digest(require_project(session, params.project_id).model_dump(mode="json"))
    identifiers = (
        params.task_ids
        if isinstance(params, AssignTasksParams)
        else ((params.task_id,) if isinstance(params, TaskIdentityParams) else ())
    )
    return content_digest([_task_state(session, identifier) for identifier in sorted(identifiers)])


def _task_state(session: Session, task_id: str) -> str:
    task = require_task(session, task_id)
    assignments = [
        row.payload
        for row in session.scalars(
            select(ProductionAssignmentRow)
            .where(
                ProductionAssignmentRow.task_id == task_id,
                ProductionAssignmentRow.active.is_(True),
            )
            .order_by(ProductionAssignmentRow.id)
        )
    ]
    project = session.get(ProductionProjectRow, task.project_id)
    values = JsonDocument.model_validate(
        {
            "task": task_view(task).model_dump(mode="json"),
            "assignments": assignments,
            "project": project.payload if project else None,
        }
    )
    return content_digest(values.root)
