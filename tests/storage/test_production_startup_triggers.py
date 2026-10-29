# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Restarts keep production history guards without trigger DDL behind open row writers."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from datakeel.storage.database import Database

_GUARDS = {
    "production_revisions": ("production_revisions_immutable", "datakeel_immutable_production"),
    "production_reviews": ("production_reviews_immutable", "datakeel_immutable_production"),
    "production_label_sets": ("datakeel_label_set_immutable", "datakeel_immutable_label_set"),
}


def _bound_functions(db: Database) -> dict[str, str]:
    with db.engine.connect() as connection:
        return {
            table: str(
                connection.scalar(
                    text(
                        "SELECT tgfoid::regproc::text FROM pg_trigger "
                        "WHERE tgname = :name AND tgrelid = CAST(:table AS regclass)"
                    ),
                    {"name": name, "table": table},
                )
            )
            for table, (name, _) in _GUARDS.items()
        }


def test_restart_with_current_production_guards_needs_no_writer_blocking_ddl(
    db: Database,
) -> None:
    """Row writers hold their table locks while a second startup completes unchanged."""
    if db.sqlite:
        db.migrate()
        return
    expected = {table: function for table, (_, function) in _GUARDS.items()}
    assert _bound_functions(db) == expected
    with db.engine.connect() as writer, ThreadPoolExecutor(max_workers=1) as pool:
        transaction = writer.begin()
        try:
            for table in _GUARDS:
                writer.execute(text(f"LOCK TABLE {table} IN ROW EXCLUSIVE MODE"))
            pool.submit(db.migrate).result(timeout=15)
        finally:
            transaction.rollback()
    assert _bound_functions(db) == expected


def test_restart_rebinds_production_guards_left_on_another_function(db: Database) -> None:
    """A trigger pointing at another guard function is replaced by the production guard."""
    if db.sqlite:
        return
    with db.engine.begin() as connection:
        for table, (name, _) in _GUARDS.items():
            connection.execute(
                text(
                    f"DROP TRIGGER {name} ON {table}; "
                    f"CREATE TRIGGER {name} BEFORE UPDATE OR DELETE ON {table} "
                    "FOR EACH ROW EXECUTE FUNCTION datakeel_immutable_event()"
                )
            )
    db.migrate()
    assert _bound_functions(db) == {table: function for table, (_, function) in _GUARDS.items()}
