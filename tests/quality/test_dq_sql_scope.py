# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""SQL assertion reads stay on the frozen target despite aliases and schema shadowing."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.schema import CreateSchema, DropSchema

from datakeel.core.catalog_models import SourceProperties
from datakeel.core.dq_models import DqParameters, DqRule, DqTarget
from datakeel.core.errors import ValidationError
from datakeel.core.metric_models import CompiledQuery, QueryLimits, QueryResult
from datakeel.quality.dq_engine import execute_rule
from datakeel.quality.dq_source import execute_assertion, validate_assertion

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from sqlalchemy.engine import Engine
    from sqlalchemy.engine.interfaces import DBAPIConnection
    from sqlalchemy.pool import ConnectionPoolEntry

    from datakeel.storage.database import Database


def _postgres_source(
    db: Database,
    target_amount: int,
    shadow: str,
) -> tuple[SourceProperties, str]:
    schema = "DqTarget_" + uuid4().hex
    with db.engine.begin() as connection:
        for name, amount in ((schema, target_amount), (shadow, -target_amount)):
            connection.execute(CreateSchema(name))
            connection.execute(
                text("SELECT set_config('search_path', :schema, true)"),
                {"schema": db.engine.dialect.identifier_preparer.quote(name)},
            )
            connection.execute(text("CREATE TABLE orders(amount INTEGER)"))
            connection.execute(text("INSERT INTO orders VALUES (:amount)"), {"amount": amount})
    return SourceProperties(
        connection_url=db.engine.url.render_as_string(hide_password=False), dialect="postgresql"
    ), schema


@pytest.fixture
def shadowed_source(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_amount: int,
) -> Iterator[tuple[SourceProperties, DqTarget]]:
    """Give the default schema an opposite row without touching shared schemas or tables."""
    shadow = "dq_shadow_" + uuid4().hex
    if db.sqlite:
        path = tmp_path / "source.sqlite"
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE orders(amount INTEGER)")
            connection.execute("INSERT INTO orders VALUES (?)", (target_amount,))
        source = SourceProperties(connection_url=f"sqlite:///{path}", dialect="sqlite")
        schema = "main"
    else:
        source, schema = _postgres_source(db, target_amount, shadow)

    def engine_with_shadow(*args: object, **kwargs: object) -> Engine:
        engine = create_engine(*args, **kwargs)

        @event.listens_for(engine, "connect")
        def default_schema(raw: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
            cursor = raw.cursor()
            if db.sqlite:
                cursor.execute("CREATE TEMP TABLE orders(amount INTEGER)")
                cursor.execute("INSERT INTO orders VALUES (?)", (-target_amount,))
            else:
                cursor.execute("SELECT set_config('search_path', %s, false)", (shadow,))
            raw.commit()
            cursor.close()

        return engine

    monkeypatch.setattr("datakeel.metrics.execution.create_engine", engine_with_shadow)
    try:
        yield source, DqTarget(source_id="demo", schema_name=schema, table="orders")
    finally:
        if not db.sqlite:
            with db.engine.begin() as connection:
                # Only this fixture's newly generated UUID schema is removed.
                connection.execute(DropSchema(shadow, cascade=True))
                connection.execute(DropSchema(schema, cascade=True))


@pytest.mark.parametrize("target_amount", [-7, 7])
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT o.amount FROM orders o WHERE o.amount < :floor",
        "SELECT a.amount FROM orders a JOIN orders b ON a.amount=b.amount WHERE b.amount < :floor",
        (
            "SELECT a.amount FROM orders a WHERE EXISTS (SELECT 1 FROM orders b "
            "WHERE a.amount=b.amount AND b.amount < :floor)"
        ),
        'SELECT o.amount FROM "{{schema}}"."orders" o WHERE o.amount < :floor',
        "SELECT o.amount FROM {{schema}}.orders o WHERE o.amount < :floor",
        "SELECT /* 只读 订单 */ o.amount FROM orders o WHERE o.amount < :floor",
    ],
)
def test_assertion_aliases_and_subqueries_read_frozen_schema(
    shadowed_source: tuple[SourceProperties, DqTarget],
    target_amount: int,
    sql: str,
) -> None:
    """Opposite default data cannot change either declared-target verdict."""
    source, target = shadowed_source
    sql = sql.replace("{{schema}}", target.schema_name or "main")
    rule = DqRule(
        id="scoped",
        name="Scoped assertion",
        kind="sql_assertion",
        target=target,
        owner="quality-team",
        params=DqParameters(sql=sql, bindings={"floor": 0}),
    )
    result = execute_rule(rule, source)
    assert result.status == ("failed" if target_amount < 0 else "passed")
    assert result.failed_count == int(target_amount < 0)


def test_assertion_qualified_rewrite_preserves_named_binds_and_non_table_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PostgreSQL table qualification never rewrites :name binds, comments or string contents."""
    seen: list[str] = []

    def capture(_url: str, query: CompiledQuery, _limits: QueryLimits) -> QueryResult:
        seen.append(query.sql)
        return QueryResult(columns=["amount"], rows=[])

    monkeypatch.setattr("datakeel.quality.dq_source.execute_query", capture)
    sql = (
        'SELECT \'订单 orders :literal\' AS note, o.amount FROM "订单""orders" o '
        "/* 保留 :comment */ WHERE o.amount < :floor"
    )
    rule = DqRule(
        id="bound",
        name="Bound SQL",
        owner="quality-team",
        kind="sql_assertion",
        target=DqTarget(source_id="demo", schema_name="MixedSchema", table='订单"orders'),
        params=DqParameters(sql=sql, bindings={"floor": 0}),
    )
    execute_assertion(
        rule,
        SourceProperties(connection_url="postgresql://unused.invalid/local", dialect="postgresql"),
    )
    assert seen[-1] == sql.replace('FROM "订单""orders" o', 'FROM "MixedSchema"."订单""orders" o')
    assert ":floor" in seen[-1]
    assert "%(floor)s" not in seen[-1]


def test_sqlite_attached_schema_cannot_fall_back_to_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicitly attached target is used for both bounded preflight and actual assertions."""
    primary, attached = tmp_path / "primary.sqlite", tmp_path / "attached.sqlite"
    for path, amount in ((primary, 7), (attached, -7)):
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE orders(amount INTEGER)")
            connection.execute("INSERT INTO orders VALUES (?)", (amount,))

    def attached_engine(*args: object, **kwargs: object) -> Engine:
        engine = create_engine(*args, **kwargs)

        @event.listens_for(engine, "connect")
        def attach(raw: DBAPIConnection, _record: ConnectionPoolEntry) -> None:
            cursor = raw.cursor()
            cursor.execute("ATTACH DATABASE ? AS archive", (f"file:{attached}?mode=ro",))
            cursor.close()

        return engine

    monkeypatch.setattr("datakeel.metrics.execution.create_engine", attached_engine)
    rule = DqRule(
        id="attached",
        name="Attached target",
        owner="quality-team",
        kind="sql_assertion",
        target=DqTarget(source_id="demo", schema_name="archive", table="orders"),
        params=DqParameters(
            sql="SELECT amount FROM orders WHERE amount < :floor", bindings={"floor": 0}
        ),
    )
    result = execute_rule(
        rule, SourceProperties(connection_url=f"sqlite:///{primary}", dialect="sqlite")
    )
    assert result.status == "failed"
    assert result.failed_count == 1


@pytest.mark.parametrize(
    "sql",
    [
        "WITH unused AS (SELECT 1) SELECT * FROM orders",
        "SELECT * FROM another.main.orders",
        "SELECT * FROM temp.orders",
    ],
)
def test_assertion_scope_rejects_ctes_other_schemas_and_catalogs(sql: str) -> None:
    """Qualification does not grant access to a different table namespace or derived CTE."""
    rule = DqRule(
        id="reject",
        name="Reject scope",
        owner="quality-team",
        kind="sql_assertion",
        target=DqTarget(source_id="demo", schema_name="main", table="orders"),
        params=DqParameters(sql=sql),
    )
    with pytest.raises(ValidationError):
        validate_assertion(rule, SourceProperties(dialect="sqlite"))
