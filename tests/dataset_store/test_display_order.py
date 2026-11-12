# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persisted display ranks are written once and never rewritten by later calls."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select, update

from datakeel.dataset_store.display_order import persist_task_ranks
from datakeel.storage.production_rows import ProductionTaskRow
from tests.production_helpers import production_fixture

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def _ranks(db: Database, project_id: str) -> list[int | None]:
    with db.session() as session:
        return list(
            session.scalars(
                select(ProductionTaskRow.display_rank)
                .where(ProductionTaskRow.project_id == project_id)
                .order_by(ProductionTaskRow.id)
            )
        )


def test_persist_task_ranks_keeps_existing_values(db: Database) -> None:
    """Once every row is ranked the helper returns without touching the stored order."""
    project, _ = production_fixture(db, "group", count=3)
    with db.session() as session:
        session.execute(
            update(ProductionTaskRow)
            .where(ProductionTaskRow.project_id == project.id)
            .values(display_rank=99)
        )
        session.commit()
    with db.session() as session:
        persist_task_ranks(session, project.id)
        session.commit()
    assert _ranks(db, project.id) == [99, 99, 99]


def test_persist_task_ranks_backfill_is_idempotent(db: Database) -> None:
    """A repeated backfill writes the same total order instead of shifting ranks."""
    project, _ = production_fixture(db, "group", count=4, package_size=2)
    with db.session() as session:
        session.execute(
            update(ProductionTaskRow)
            .where(ProductionTaskRow.project_id == project.id)
            .values(display_rank=None)
        )
        session.commit()
    with db.session() as session:
        persist_task_ranks(session, project.id)
        session.commit()
    first = _ranks(db, project.id)
    assert sorted(first) == [0, 1, 2, 3]
    with db.session() as session:
        persist_task_ranks(session, project.id)
        session.commit()
    assert _ranks(db, project.id) == first


def test_persist_task_ranks_accepts_a_project_without_tasks(db: Database) -> None:
    """An unsplit project has no rows to rank and the helper returns quietly."""
    project, _ = production_fixture(db, "group", split=False)
    with db.session() as session:
        persist_task_ranks(session, project.id)
        session.commit()
    assert _ranks(db, project.id) == []
