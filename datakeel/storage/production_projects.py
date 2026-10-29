# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Create projects and deterministic packages without duplicating source samples."""

import json
from collections import defaultdict
from pathlib import PurePosixPath

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from datakeel.actions.production_parameters import (
    CreateProjectParams,
    SplitPackagesParams,
    UpgradeProjectParams,
)
from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.models import FileItem, new_id, utcnow
from datakeel.core.production_models import Project, TaskPackage
from datakeel.storage.annotation_store import require_annotation_version
from datakeel.storage.production_catalog import require_label_set, require_template
from datakeel.storage.production_rows import (
    ProductionMemberRow,
    ProductionPackageRow,
    ProductionProjectRow,
    ProductionSummaryRow,
    ProductionTaskRow,
)
from datakeel.storage.production_tasks import initialize_summary, require_mutable_project

REVIEW_SUGGESTION_MEMBERS = 2


def create_project(session: Session, params: CreateProjectParams, actor: str) -> Project:
    """Create an approved project only against real input and published annotation rules."""
    require_annotation_version(session, params.dataset_id, params.version_id)
    require_label_set(session, params.label_set_id, params.label_set_version)
    if params.template_id is not None:
        require_template(session, params.template_id)
    project = Project(id=new_id(), created_at=utcnow(), **params.model_dump(exclude={"request_id"}))
    session.add(
        ProductionProjectRow(
            id=project.id, dataset_id=project.dataset_id, payload=project.model_dump(mode="json")
        )
    )
    session.flush()
    session.add(ProductionMemberRow(project_id=project.id, actor=actor))
    initialize_summary(session, project.id)
    return project


def record_project_member(session: Session, project_id: str, actor: str) -> bool:
    """Return the review suggestion exactly once when a second participant first appears."""
    row = session.get(
        ProductionProjectRow, project_id, with_for_update=True, populate_existing=True
    )
    if row is None:
        require_mutable_project(session, project_id)
        return False
    if session.get(ProductionMemberRow, (project_id, actor)) is not None:
        return False
    session.add(ProductionMemberRow(project_id=project_id, actor=actor))
    session.flush()
    count = (
        session.scalar(
            select(func.count())
            .select_from(ProductionMemberRow)
            .where(ProductionMemberRow.project_id == project_id)
        )
        or 0
    )
    project = Project.model_validate(row.payload)
    suggest = count >= REVIEW_SUGGESTION_MEMBERS and not project.review_prompt_shown
    if suggest:
        row.payload = project.model_copy(update={"review_prompt_shown": True}).model_dump(
            mode="json"
        )
    return suggest


def _groups(files: list[FileItem], params: SplitPackagesParams) -> list[list[FileItem]]:
    groups: defaultdict[str, list[FileItem]] = defaultdict(list)
    for item in sorted(files, key=lambda entry: (entry.path, entry.id)):
        key = "all"
        if params.group_by == "directory":
            key = str(PurePosixPath(item.path).parent)
        elif params.group_by == "metadata":
            if params.metadata_field is None:
                message = "Metadata grouping requires metadata_field"
                raise ValidationError(message)
            key = json.dumps(item.metadata.get(params.metadata_field), sort_keys=True)
        groups[key].append(item)
    return [
        values[start : start + params.package_size]
        for _, values in sorted(groups.items())
        for start in range(0, len(values), params.package_size)
    ]


def split_packages(session: Session, params: SplitPackagesParams) -> tuple[TaskPackage, ...]:
    """Split a project's immutable source once in reproducible path and sample order."""
    session.get(
        ProductionProjectRow, params.project_id, with_for_update=True, populate_existing=True
    )
    project = require_mutable_project(session, params.project_id)
    if (
        session.scalar(
            select(ProductionPackageRow.id)
            .where(ProductionPackageRow.project_id == project.id)
            .limit(1)
        )
        is not None
    ):
        message = "Project was already split; repeat the original request_id to replay"
        raise ConflictError(message)
    version = require_annotation_version(session, project.dataset_id, project.version_id)
    files = [FileItem.model_validate(item) for item in version.manifest]
    packages = tuple(
        _create_package(session, project, group, params, ordinal)
        for ordinal, group in enumerate(_groups(files, params))
    )
    session.execute(
        update(ProductionSummaryRow)
        .where(ProductionSummaryRow.scope_id == project.id, ProductionSummaryRow.state == "pending")
        .values(count=len(files))
    )
    return packages


def _create_package(
    session: Session,
    project: Project,
    files: list[FileItem],
    params: SplitPackagesParams,
    ordinal: int,
) -> TaskPackage:
    package = TaskPackage(
        id=new_id(),
        project_id=project.id,
        name=f"Package {ordinal + 1}",
        task_count=len(files),
        split_rule=params.group_by,
        created_at=utcnow(),
    )
    session.add(
        ProductionPackageRow(
            id=package.id, project_id=project.id, payload=package.model_dump(mode="json")
        )
    )
    session.flush()
    initialize_summary(session, package.id, len(files))
    session.add_all(
        ProductionTaskRow(
            id=new_id(),
            project_id=project.id,
            package_id=package.id,
            sample_id=item.id,
            state="pending",
            round=0,
            priority=0,
        )
        for item in files
    )
    return package


def upgrade_project(session: Session, params: UpgradeProjectParams) -> Project:
    """Upgrade in place; reject downgrades because they would discard required review semantics."""
    row = session.get(
        ProductionProjectRow, params.project_id, with_for_update=True, populate_existing=True
    )
    project = require_mutable_project(session, params.project_id)
    tiers = ("personal", "group", "team")
    if tiers.index(params.workflow_tier) < tiers.index(project.workflow_tier):
        message = "Workflow downgrades are unsupported because review obligations must be preserved"
        raise ValidationError(message)
    upgraded = project.model_copy(update={"workflow_tier": params.workflow_tier})
    if row is not None:
        row.payload = upgraded.model_dump(mode="json")
    return upgraded
