# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve production references back to version-pinned dataset access policies."""

from sqlalchemy.orm import Session

from datakeel.core.models import AssetRef
from datakeel.core.production_models import Project
from datakeel.storage.production_catalog_rows import ProductionPrelabelRunRow
from datakeel.storage.production_rows import (
    ProductionAssignmentRow,
    ProductionPackageRow,
    ProductionProjectRow,
    ProductionReviewRow,
    ProductionRevisionRow,
    ProductionTaskRow,
)


def production_targets(session: Session, ref: AssetRef) -> tuple[AssetRef, ...]:
    """Require the same source grant for task, revision, review, package and run projections."""
    project_id = _project_id(session, ref)
    if project_id is None:
        return ()
    row = session.get(ProductionProjectRow, project_id)
    if row is None:
        return ()
    project = Project.model_validate(row.payload)
    return (AssetRef(asset_id=project.dataset_id, version=project.version_id),)


def _project_id(session: Session, ref: AssetRef) -> str | None:
    if ref.asset_type == "project":
        return ref.asset_id
    if ref.asset_type == "assignment":
        assignment = session.get(ProductionAssignmentRow, ref.asset_id)
        task = session.get(ProductionTaskRow, assignment.task_id) if assignment else None
        return task.project_id if task else None
    return _parent_project_id(session, ref)


def _parent_project_id(session: Session, ref: AssetRef) -> str | None:
    if ref.asset_type == "task_package":
        package = session.get(ProductionPackageRow, ref.asset_id)
        return package.project_id if package else None
    if ref.asset_type == "production_task":
        task = session.get(ProductionTaskRow, ref.asset_id)
        return task.project_id if task else None
    if ref.asset_type == "annotation_revision":
        revision = session.get(ProductionRevisionRow, ref.asset_id)
        return revision.project_id if revision else None
    if ref.asset_type == "review":
        review = session.get(ProductionReviewRow, ref.asset_id)
        return review.project_id if review else None
    if ref.asset_type == "prelabel_run":
        run = session.get(ProductionPrelabelRunRow, ref.asset_id)
        return run.project_id if run else None
    return None
