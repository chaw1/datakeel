# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate migration completeness and count exact current annotation instances."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.errors import ValidationError
from datakeel.core.production_catalog_models import LabelSet
from datakeel.core.production_models import AnnotationRevision, Project
from datakeel.storage.production_catalog import annotation_categories
from datakeel.storage.production_rows import (
    ProductionProjectRow,
    ProductionRevisionRow,
    ProductionTaskRow,
)


def validate_migration(before: LabelSet, after: LabelSet) -> None:
    """Require explicit decisions for every removed or renamed stable label identity."""
    if before.version >= after.version or before.id != after.id:
        message = "Label migration requires an earlier version of the same label set"
        raise ValidationError(message)
    old = {label.id: label for label in before.labels}
    new = {label.id: label for label in after.labels}
    sources: set[str] = set()
    for step in after.migration:
        if not set(step.source_ids) <= old.keys() or not set(step.target_ids) <= new.keys():
            message = "Migration references unknown source or target label identities"
            raise ValidationError(message)
        if (set(step.source_ids) - set(step.target_ids)) & new.keys():
            message = "Removed migration source identities cannot remain in the new label set"
            raise ValidationError(message)
        if sources & set(step.source_ids) or len(set(step.source_ids)) != len(step.source_ids):
            message = "Each old label may have only one migration decision"
            raise ValidationError(message)
        sources.update(step.source_ids)
    changed = {key for key in old if key not in new or old[key].name != new[key].name}
    if not changed <= sources:
        message = "Removed and renamed labels require a complete migration plan"
        raise ValidationError(message)


def migration_impact(session: Session, before: LabelSet, after: LabelSet) -> tuple[int, int]:
    """Count affected label instances and current revisions in projects pinned to the old version.

    Each label, box and span is one annotation. Historical superseded revisions are
    immutable evidence and are not migration targets. A task's latest revision is
    counted once, even when several migration decisions affect it.
    """
    source_ids = {source for step in after.migration for source in step.source_ids}
    categories = {
        value
        for label in before.labels
        if label.id in source_ids
        for value in (label.id, label.name)
    }
    project_ids = [
        row.id
        for row in session.scalars(select(ProductionProjectRow))
        if (project := Project.model_validate(row.payload)).label_set_id == before.id
        and project.label_set_version == before.version
    ]
    annotations = revisions = 0
    statement = (
        select(ProductionRevisionRow)
        .join(ProductionTaskRow, ProductionTaskRow.latest_revision_id == ProductionRevisionRow.id)
        .where(ProductionTaskRow.project_id.in_(project_ids))
    )
    for row in session.scalars(statement):
        revision = AnnotationRevision.model_validate(row.payload)
        count = sum(value in categories for value in annotation_categories(revision.annotation))
        annotations += count
        revisions += bool(count)
    return annotations, revisions
