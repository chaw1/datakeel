# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Protect historical skeleton point identities during template edits and project upgrades."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.errors import ValidationError
from datakeel.core.production_catalog_models import ProductionTemplate
from datakeel.core.production_keypoints import enabled_components, require_schema
from datakeel.core.production_models import AnnotationRevision, Project
from datakeel.storage.production_rows import (
    ProductionProjectRow,
    ProductionRevisionRow,
)


def require_writable_template(template: ProductionTemplate) -> None:
    """Reject legacy keypoint placeholders for new template versions and project creation."""
    if "keypoints" in enabled_components(template):
        require_schema(template)


def validate_point_removal(
    session: Session,
    before: ProductionTemplate | None,
    after: ProductionTemplate,
    *,
    project_id: str | None = None,
) -> None:
    """Reject deleting or renaming any point used by an immutable historical revision."""
    if before is None or before.keypoint_schema is None:
        return
    old_ids = {point.id for point in before.keypoint_schema.points}
    new_ids: set[str] = (
        {point.id for point in after.keypoint_schema.points} if after.keypoint_schema else set()
    )
    removed = old_ids - new_ids
    if not removed or before.id != after.id:
        return
    used = _used_points(session, before.id, removed, project_id=project_id)
    if used:
        message = "Cannot delete or rename keypoints used by existing revisions: " + ", ".join(used)
        raise ValidationError(message)


def _used_points(
    session: Session, template_id: str, removed: set[str], *, project_id: str | None
) -> tuple[str, ...]:
    used: set[str] = set()
    for revision in _revisions(session, _project_ids(session, template_id, project_id)):
        for skeleton in revision.annotation.keypoints or ():
            used.update(point.id for point in skeleton.points if point.id in removed)
        if used == removed:
            break
    return tuple(sorted(used))


def _project_ids(session: Session, template_id: str, project_id: str | None) -> tuple[str, ...]:
    if project_id is not None:
        return (project_id,)
    rows = session.scalars(select(ProductionProjectRow)).all()
    return tuple(
        project.id
        for project in (Project.model_validate(row.payload) for row in rows)
        if project.template_id == template_id
    )


def _revisions(session: Session, project_ids: Iterable[str]) -> Iterable[AnnotationRevision]:
    identifiers = tuple(project_ids)
    if not identifiers:
        return ()
    rows = session.scalars(
        select(ProductionRevisionRow).where(ProductionRevisionRow.project_id.in_(identifiers))
    )
    return (AnnotationRevision.model_validate(row.payload) for row in rows)
