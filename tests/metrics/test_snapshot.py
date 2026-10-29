# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Multiple bounded reads retain one source snapshot even while other writers commit."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import create_engine, event, text
from sqlglot import exp

from datakeel.core.metric_models import CompiledQuery, QueryLimits
from datakeel.metrics import execution

if TYPE_CHECKING:
    import pytest
    from sqlalchemy.engine import Engine

    from datakeel.storage.database import Database


def _interleave_write(db: Database, monkeypatch: pytest.MonkeyPatch) -> None:
    def observed_engine(*args: object, **kwargs: object) -> Engine:
        engine = create_engine(*args, **kwargs)

        @event.listens_for(engine, "after_cursor_execute")
        def after_read(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _many: object,
        ) -> None:
            if statement.startswith("SELECT value FROM"):
                with db.engine.begin() as writer:
                    writer.execute(text("INSERT INTO snapshot_values VALUES (3)"))

        return engine

    monkeypatch.setattr(execution, "create_engine", observed_engine)


def test_read_queries_use_one_snapshot_during_concurrent_insert(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A follow-up coverage count cannot observe rows absent from its associated assertion."""
    with db.engine.begin() as connection:
        if db.sqlite:
            connection.execute(text("PRAGMA journal_mode=WAL"))
        connection.execute(text("CREATE TABLE snapshot_values(value INTEGER)"))
        connection.execute(text("INSERT INTO snapshot_values VALUES (1), (2)"))
        schema = (
            "main"
            if db.sqlite
            else str(connection.execute(text("SELECT current_schema()")).scalar_one())
        )
    _interleave_write(db, monkeypatch)
    table = exp.table_("snapshot_values", db=schema, quoted=True)
    base = CompiledQuery(
        tables=["snapshot_values"],
        columns=["value"],
        metric_id="snapshot",
        metric_version=1,
        source_id="generated",
        dialect="sqlite" if db.sqlite else "postgres",
        sql=exp.select("value").from_(table).sql(),
    )
    count = base.model_copy(
        update={"sql": exp.select(exp.Count(this=exp.Star())).from_(table).sql()}
    )
    first, second = execution.execute_queries(
        db.engine.url.render_as_string(hide_password=False), (base, count), QueryLimits()
    )
    assert first.rows == [[1], [2]]
    assert second.rows == [[2]]
    with db.engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM snapshot_values")).scalar_one() == 3
