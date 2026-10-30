# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Name workbench samples from their pinned manifest and report a task's live holder state."""

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import NotFoundError
from datakeel.core.models import AssetRef, utcnow
from datakeel.core.production_models import Assignment, ProductionTask, Project
from datakeel.core.production_team_models import LeaseRelease
from datakeel.core.workbench_models import (
    SkillDispatchPreview,
    SkillDispatchPreviewRequest,
    WorkbenchLease,
    WorkbenchSampleName,
    WorkbenchTaskSampleQuery,
    WorkbenchTaskSamples,
    WorkbenchTaskStatus,
)
from datakeel.storage.data_asset_access import require_access
from datakeel.storage.database import Database, VersionRow
from datakeel.storage.production_dispatch import preview_skill_dispatch
from datakeel.storage.production_leases import LEASED_STATES, enforced_deadline
from datakeel.storage.production_rows import ProductionAssignmentRow, ProductionTaskRow
from datakeel.storage.production_tasks import require_project, task_view
from datakeel.storage.production_team_rows import ProductionLeaseReleaseRow

_RECENT_RELEASES = 10


def _relative_path(item: dict[str, object]) -> str | None:
    metadata = item.get("metadata")
    if not isinstance(metadata, dict):
        return None
    value = cast("dict[str, object]", metadata).get("relative_path")
    return value if isinstance(value, str) and value else None


def sample_names(session: Session, project: Project) -> dict[str, tuple[str, str]]:
    """Map pinned samples to their file name and path under the import root.

    Datasets imported before directory imports recorded a relative path keep the file name.
    """
    version = session.get(VersionRow, project.version_id)
    if version is None or version.dataset_id != project.dataset_id:
        return {}
    names: dict[str, tuple[str, str]] = {}
    for item in version.manifest:
        identifier, filename = item.get("id"), item.get("filename")
        if isinstance(identifier, str) and isinstance(filename, str):
            path = (_relative_path(item) or filename).replace("\\", "/")
            names[identifier] = (PurePosixPath(path).name or path, path)
    return names


def name_tasks(
    tasks: Iterable[ProductionTask], names: dict[str, tuple[str, str]]
) -> tuple[WorkbenchSampleName, ...]:
    """Pair each task with its sample's name, falling back to the sample identity."""
    result: dict[str, WorkbenchSampleName] = {}
    for task in tasks:
        name, path = names.get(task.sample_id, (task.sample_id, task.sample_id))
        result[task.id] = WorkbenchSampleName(
            task_id=task.id, sample_id=task.sample_id, name=name, path=path
        )
    return tuple(result.values())


def matches_search(
    task: ProductionTask, names: dict[str, tuple[str, str]], search: str | None
) -> bool:
    """Match a case-insensitive substring of the sample's relative path or file name."""
    if search is None:
        return True
    needle = search.casefold()
    name, path = names.get(task.sample_id, (task.sample_id, task.sample_id))
    return needle in name.casefold() or needle in path.casefold()


def named_tasks(
    session: Session, project: Project, task_ids: Iterable[str]
) -> tuple[WorkbenchSampleName, ...]:
    """Name the given tasks of one project, ignoring identities from other projects."""
    identities = sorted(set(task_ids))
    if not identities:
        return ()
    rows = session.scalars(
        select(ProductionTaskRow)
        .where(
            ProductionTaskRow.id.in_(identities),
            ProductionTaskRow.project_id == project.id,
        )
        .order_by(ProductionTaskRow.id)
    )
    return name_tasks((task_view(row) for row in rows), sample_names(session, project))


def task_samples(
    db: Database, project_id: str, caller: AccessContext, query: WorkbenchTaskSampleQuery
) -> WorkbenchTaskSamples:
    """Name requested tasks under the same project grant as the project workbench."""
    require_access(db, (AssetRef(asset_type="project", asset_id=project_id),), caller)
    with db.session() as session:
        project = require_project(session, project_id)
        return WorkbenchTaskSamples(items=named_tasks(session, project, query.task_id))


def _leases(
    rows: Iterable[ProductionAssignmentRow], task: ProductionTask, project: Project, now: datetime
) -> tuple[WorkbenchLease, ...]:
    leases: list[WorkbenchLease] = []
    for row in rows:
        assignment = Assignment.model_validate(row.payload)
        if not row.active or task.state not in LEASED_STATES[assignment.stage]:
            continue
        deadline = enforced_deadline(row, assignment)
        leases.append(
            WorkbenchLease(
                assignment_id=assignment.id,
                actor=assignment.actor,
                stage=assignment.stage,
                expires_at=deadline,
                seconds_remaining=(deadline - now).total_seconds(),
                enforced=project.workflow_tier == "team" and row.lease_expires_at is not None,
            )
        )
    return tuple(leases)


def task_status(db: Database, task_id: str, caller: AccessContext) -> WorkbenchTaskStatus:
    """Read a task's state, assignments, effective leases and recent releases cheaply."""
    require_access(db, (AssetRef(asset_type="production_task", asset_id=task_id),), caller)
    now = utcnow()
    with db.session() as session:
        row = session.get(ProductionTaskRow, task_id)
        if row is None:
            message = "Production task was not found"
            raise NotFoundError(message)
        task = task_view(row)
        project = require_project(session, task.project_id)
        rows = tuple(
            session.scalars(
                select(ProductionAssignmentRow).where(ProductionAssignmentRow.task_id == task_id)
            )
        )
        releases = session.scalars(
            select(ProductionLeaseReleaseRow.payload)
            .where(ProductionLeaseReleaseRow.task_id == task_id)
            .order_by(
                ProductionLeaseReleaseRow.released_at.desc(),
                ProductionLeaseReleaseRow.assignment_id,
            )
            .limit(_RECENT_RELEASES)
        )
        return WorkbenchTaskStatus(
            task=task,
            assignments=tuple(Assignment.model_validate(item.payload) for item in rows),
            leases=_leases(rows, task, project, now),
            releases=tuple(LeaseRelease.model_validate(payload) for payload in releases),
            observed_at=now.astimezone(UTC),
        )


def dispatch_preview(
    db: Database, project_id: str, caller: AccessContext, request: SkillDispatchPreviewRequest
) -> SkillDispatchPreview:
    """Preview a skill dispatch for a readable project without locking or writing anything."""
    require_access(db, (AssetRef(asset_type="project", asset_id=project_id),), caller)
    with db.session() as session:
        return preview_skill_dispatch(session, project_id, request)
