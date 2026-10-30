# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Databases from before template locking keep their behaviour after migrating, once."""

from pathlib import Path

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DatabaseError

from datakeel.core.errors import ValidationError
from datakeel.core.production_catalog_models import ProductionTemplate
from datakeel.storage.database import Database
from datakeel.storage.production_catalog_rows import (
    ProductionTemplateRow,
    ProductionTemplateVersionRow,
)
from datakeel.storage.production_queries import get_project
from datakeel.storage.production_rows import ProductionProjectRow
from tests.storage.template_lock_support import (
    REQUIRED_COLOUR,
    TEMPLATE,
    box,
    change_template,
    save,
    seed_two_projects,
)


def _make_legacy(db: Database) -> None:
    """Rewind to the v0.18.0 shape: one in-place template row at revision 2, no locks."""
    with db.engine.begin() as connection:
        connection.execute(text("DROP TABLE production_template_versions"))
        row = connection.execute(
            select(ProductionTemplateRow.payload).where(ProductionTemplateRow.id == TEMPLATE)
        ).scalar_one()
        edited = ProductionTemplate.model_validate(
            {**row, "revision": 2, "attributes": [REQUIRED_COLOUR]}
        )
        connection.execute(
            update(ProductionTemplateRow)
            .where(ProductionTemplateRow.id == TEMPLATE)
            .values(revision=2, payload=edited.model_dump(mode="json"))
        )
        for identifier, payload in connection.execute(
            select(ProductionProjectRow.id, ProductionProjectRow.payload)
        ).all():
            legacy = {key: value for key, value in payload.items() if key != "template_version"}
            connection.execute(
                update(ProductionProjectRow)
                .where(ProductionProjectRow.id == identifier)
                .values(payload=legacy)
            )


def _snapshot(db: Database) -> tuple[int, list[object]]:
    with db.engine.connect() as connection:
        versions = connection.scalar(select(func.count()).select_from(ProductionTemplateVersionRow))
        projects = [
            row.payload
            for row in connection.execute(
                select(ProductionProjectRow.payload).order_by(ProductionProjectRow.id)
            )
        ]
    return int(versions or 0), projects


def test_legacy_projects_lock_to_the_revision_they_used_and_rerun_changes_nothing(
    db: Database, tmp_path: Path
) -> None:
    """Migration locks every project at the template's current revision exactly once."""
    (first, tasks), (second, _) = seed_two_projects(db, tmp_path / "src")
    _make_legacy(db)
    db.migrate()
    assert get_project(db, first.id).template_version == 2
    assert get_project(db, second.id).template_version == 2
    migrated = _snapshot(db)
    assert migrated[0] == 1
    db.migrate()
    assert _snapshot(db) == migrated
    with pytest.raises(ValidationError, match="colour"):
        save(db, tasks[0], [box("cat")])
    save(db, tasks[1], [box("cat", colour="blue")])
    change_template(db)
    assert get_project(db, first.id).template_version == 2
    with pytest.raises(ValidationError, match="colour"):
        save(db, tasks[2], [box("cat")])


def test_saved_template_versions_reject_updates_and_deletes(db: Database, tmp_path: Path) -> None:
    """A locked version cannot be rewritten underneath the projects that read it."""
    seed_two_projects(db, tmp_path / "src")
    for statement in (
        update(ProductionTemplateVersionRow).values(revision=9),
        ProductionTemplateVersionRow.__table__.delete(),
    ):
        with pytest.raises(DatabaseError, match="immutable"), db.engine.begin() as connection:
            connection.execute(statement)
