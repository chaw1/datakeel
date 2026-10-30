# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Append-only template versions and the per-project template lock.

Every template write appends a version row. A project reads the version it locked when it was
created; only a signed ``upgrade_project_template`` moves it. Databases from before the lock
existed are migrated by locking each project to its template's current revision, which is the
version it was really using, so their behaviour does not change.
"""

from typing import TYPE_CHECKING

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from datakeel.core.errors import NotFoundError
from datakeel.core.models import new_id
from datakeel.core.production_catalog_models import ProductionTemplate
from datakeel.storage.production_catalog_rows import (
    ProductionLabelSetRow,
    ProductionTemplateRow,
    ProductionTemplateVersionRow,
)
from datakeel.storage.production_rows import ProductionProjectRow

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection
    from sqlalchemy.orm import Session

    from datakeel.core.production_models import Project


def record_template_version(session: "Session", template: ProductionTemplate) -> None:
    """Append the saved revision; a revision is written exactly once and never changed."""
    exists = session.scalar(
        select(ProductionTemplateVersionRow.id).where(
            ProductionTemplateVersionRow.template_id == template.id,
            ProductionTemplateVersionRow.revision == template.revision,
        )
    )
    if exists is None:
        session.add(
            ProductionTemplateVersionRow(
                id=new_id(),
                template_id=template.id,
                revision=template.revision,
                payload=template.model_dump(mode="json"),
            )
        )
        session.flush()


def template_version(session: "Session", template_id: str, revision: int) -> ProductionTemplate:
    """Read one saved template version exactly, never silently another revision."""
    row = session.scalar(
        select(ProductionTemplateVersionRow).where(
            ProductionTemplateVersionRow.template_id == template_id,
            ProductionTemplateVersionRow.revision == revision,
        )
    )
    if row is not None:
        return ProductionTemplate.model_validate(row.payload)
    current = session.get(ProductionTemplateRow, template_id)
    if current is not None and current.revision == revision:
        return ProductionTemplate.model_validate(current.payload)
    message = f"Template {template_id} version {revision} was not found"
    raise NotFoundError(message)


def latest_template(session: "Session", template_id: str) -> ProductionTemplate:
    """Return the template's current revision, archived or not."""
    row = session.get(ProductionTemplateRow, template_id)
    if row is None:
        message = "Annotation template was not found"
        raise NotFoundError(message)
    return ProductionTemplate.model_validate(row.payload)


def locked_template(session: "Session", project: "Project") -> ProductionTemplate | None:
    """Read the project's locked template version; an unmigrated project uses the current one."""
    if project.template_id is None:
        return None
    if project.template_version is None:
        return latest_template(session, project.template_id)
    return template_version(session, project.template_id, project.template_version)


def latest_label_set_version(session: "Session", label_set_id: str) -> int | None:
    """Return the newest published version of a vocabulary, if any."""
    return session.scalar(
        select(func.max(ProductionLabelSetRow.version)).where(
            ProductionLabelSetRow.label_set_id == label_set_id,
            ProductionLabelSetRow.published.is_(True),
        )
    )


def lock_existing_templates(connection: "Connection", *, sqlite: bool) -> None:
    """Backfill versions and project locks left by databases from before template locking.

    Idempotent: only missing version rows are inserted and only projects without a lock are
    updated, so a startup on a current database writes nothing.
    """
    insert = sqlite_insert if sqlite else postgres_insert
    current: dict[str, int] = {}
    for row in connection.execute(
        select(
            ProductionTemplateRow.id, ProductionTemplateRow.revision, ProductionTemplateRow.payload
        )
    ):
        current[row.id] = row.revision
        recorded = connection.scalar(
            select(ProductionTemplateVersionRow.id).where(
                ProductionTemplateVersionRow.template_id == row.id,
                ProductionTemplateVersionRow.revision == row.revision,
            )
        )
        if recorded is None:
            connection.execute(
                insert(ProductionTemplateVersionRow)
                .values(id=new_id(), template_id=row.id, revision=row.revision, payload=row.payload)
                .on_conflict_do_nothing(index_elements=["template_id", "revision"])
            )
    for project in connection.execute(
        select(ProductionProjectRow.id, ProductionProjectRow.payload)
    ):
        payload = dict(project.payload)
        template_id = payload.get("template_id")
        if not isinstance(template_id, str) or payload.get("template_version") is not None:
            continue
        if template_id not in current:
            continue
        payload["template_version"] = current[template_id]
        connection.execute(
            update(ProductionProjectRow)
            .where(ProductionProjectRow.id == project.id)
            .values(payload=payload)
        )
