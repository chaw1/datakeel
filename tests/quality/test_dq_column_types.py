# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Special column types either evaluate correctly or are refused when a rule is prepared."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.schema import CreateSchema, DropSchema

from datakeel.actions.service import prepare_action
from datakeel.catalog.service import import_catalog
from datakeel.core.catalog_models import CatalogImportRequest, SourceProperties
from datakeel.core.dq_models import DqParameters, DqRule, DqTarget
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument
from datakeel.quality.dq_engine import execute_rule
from datakeel.quality.dq_types import check_column_types, column_category
from datakeel.storage.dq_reads import read_rules

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from datakeel.core.dq_models import DqKind
    from datakeel.storage.database import Database

FIRST, SECOND, ORPHAN = (
    "00000000-0000-4000-8000-000000000001",
    "00000000-0000-4000-8000-000000000002",
    "00000000-0000-4000-8000-000000000003",
)


@pytest.mark.parametrize(
    ("type_name", "dialect", "category"),
    [
        ("UUID", "postgresql", "uuid"),
        ("JSONB", "postgresql", "json"),
        ("JSON", "postgresql", "json"),
        ("NUMERIC(12, 4)", "postgresql", "numeric"),
        ("DOUBLE PRECISION", "postgresql", "numeric"),
        ("TIMESTAMP", "postgresql", "temporal"),
        ("DATE", "postgresql", "temporal"),
        ("TIME", "postgresql", "time"),
        ("ARRAY", "postgresql", "array"),
        ("INTEGER[]", "postgresql", "array"),
        ("BYTEA", "postgresql", "binary"),
        ("INTERVAL", "postgresql", "interval"),
        ("VARCHAR(3)", "postgresql", "text"),
        ("INET", "postgresql", "other"),
        ("NULL", "postgresql", "other"),
        ("BLOB", "sqlite", "binary"),
        ("TEXT", "sqlite", "dynamic"),
        ("NULL", "sqlite", "dynamic"),
    ],
)
def test_reflected_types_map_to_categories(type_name: str, dialect: str, category: str) -> None:
    """PostgreSQL types are classified exactly; SQLite stays dynamic apart from BLOB."""
    assert column_category(type_name, dialect) == category


def _rule(kind: DqKind, params: DqParameters | None = None, column: str = "value") -> DqRule:
    return DqRule(
        id="typed",
        name="Typed rule",
        owner="quality-team",
        kind=kind,
        target=DqTarget(source_id="demo", table="items", column=column),
        params=params or DqParameters(),
    )


@pytest.mark.parametrize(
    ("kind", "params", "type_name", "accepted"),
    [
        ("not_null", None, "JSONB", True),
        ("distribution_drift", DqParameters(statistic="null_rate"), "BYTEA", True),
        ("unique", None, "UUID", True),
        ("accepted_values", DqParameters(values=(FIRST,)), "UUID", True),
        ("regex", DqParameters(pattern="[0-9a-f-]+"), "UUID", True),
        ("freshness", None, "TIMESTAMP", True),
        ("range", DqParameters(minimum=0), "NUMERIC", True),
        ("range", DqParameters(minimum=0), "UUID", False),
        ("unique", None, "JSONB", False),
        ("regex", DqParameters(pattern=".*"), "JSON", False),
        ("freshness", None, "TEXT", False),
        ("distribution_drift", DqParameters(statistic="mean"), "TIMESTAMP", False),
        ("accepted_values", DqParameters(values=("x",)), "INTEGER[]", False),
    ],
)
def test_postgres_kind_and_type_compatibility(
    kind: DqKind, params: DqParameters | None, type_name: str, *, accepted: bool
) -> None:
    """Each kind accepts only column types whose values it can evaluate."""
    rule = _rule(kind, params)
    if accepted:
        check_column_types(rule, type_name, "postgresql")
    else:
        with pytest.raises(ValidationError, match="rules need"):
            check_column_types(rule, type_name, "postgresql")


def test_reference_column_must_be_comparable() -> None:
    """A UUID foreign key may reference text or UUID keys, but not numbers."""
    rule = _rule(
        "referential_integrity", DqParameters(reference_table="ref", reference_column="key")
    )
    check_column_types(rule, "UUID", "postgresql", "UUID")
    check_column_types(rule, "UUID", "postgresql", "TEXT")
    with pytest.raises(ValidationError, match="not comparable"):
        check_column_types(rule, "UUID", "postgresql", "INTEGER")
    with pytest.raises(ValidationError, match="unsupported type"):
        check_column_types(rule, "UUID", "postgresql", "JSONB")


@pytest.fixture
def typed_source(db: Database, tmp_path: Path) -> Iterator[tuple[SourceProperties, str]]:
    """Register a business table with UUID / JSONB columns (PostgreSQL) or a BLOB (SQLite)."""
    if db.sqlite:
        path = tmp_path / "typed.sqlite"
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE items(id INTEGER, value BLOB, payload BLOB)")
            connection.execute("CREATE TABLE parents(key BLOB)")
            connection.executemany(
                "INSERT INTO items VALUES (?, ?, ?)",
                [(1, b"\x00", b"\x01"), (2, b"\x00", None), (3, None, b"\x02")],
            )
        url, schema = f"sqlite:///{path}", "main"
    else:
        url = db.engine.url.render_as_string(hide_password=False)
        schema = "dq_types_" + uuid4().hex
        with db.engine.begin() as connection:
            connection.execute(CreateSchema(schema))
            connection.execute(
                text("SELECT set_config('search_path', :schema, true)"), {"schema": schema}
            )
            connection.execute(text("CREATE TABLE items(id INTEGER, value UUID, payload JSONB)"))
            connection.execute(text("CREATE TABLE parents(key UUID)"))
            connection.execute(
                text(
                    "INSERT INTO items VALUES (1, CAST(:a AS UUID), CAST('null' AS JSONB)), "
                    "(2, CAST(:a AS UUID), NULL), (3, CAST(:c AS UUID), CAST('{}' AS JSONB)), "
                    "(4, NULL, CAST('[1]' AS JSONB))"
                ),
                {"a": FIRST, "c": ORPHAN},
            )
            connection.execute(
                text("INSERT INTO parents VALUES (CAST(:a AS UUID)), (CAST(:b AS UUID))"),
                {"a": FIRST, "b": SECOND},
            )
    import_catalog(
        db,
        CatalogImportRequest(
            source_id="typed",
            name="Typed business source",
            connection_url=url,
            schemas=() if db.sqlite else (schema,),
        ),
    )
    try:
        yield (
            SourceProperties(connection_url=url, dialect="sqlite" if db.sqlite else "postgresql"),
            schema,
        )
    finally:
        if not db.sqlite:
            with db.engine.begin() as connection:
                # Only this fixture's newly generated UUID schema is removed.
                connection.execute(DropSchema(schema, cascade=True))


def _prepare(db: Database, rule: DqRule) -> DqRule:
    plan = prepare_action(
        db, "create_quality_rule", JsonDocument({"rule": rule.model_dump(mode="json")})
    )
    return DqRule.model_validate(plan.canonical_params["rule"])


def _refusal(db: Database, rule: DqRule) -> str:
    # Plain assertions on the message keep refusal regressions measurable by mutation tests.
    try:
        _prepare(db, rule)
    except ValidationError as error:
        return str(error)
    return ""


def _typed_rule(
    schema: str, kind: DqKind, column: str, params: DqParameters | None = None
) -> DqRule:
    return DqRule(
        id=f"typed-{kind}-{column}".replace("_", "-"),
        name="Typed rule",
        owner="quality-team",
        kind=kind,
        target=DqTarget(source_id="typed", schema_name=schema, table="items", column=column),
        params=params or DqParameters(),
    )


def test_special_columns_run_or_are_refused_at_preparation(
    db: Database, typed_source: tuple[SourceProperties, str]
) -> None:
    """NULL checks read no values; UUID rules compare canonical text; others are refused."""
    source, schema = typed_source
    regex = _typed_rule(schema, "regex", "payload", DqParameters(pattern=".*"))
    assert "regex rules need" in _refusal(db, regex)
    for column in ("value", "payload"):
        prepared = _prepare(db, _typed_rule(schema, "not_null", column))
        result = execute_rule(prepared, source)
        assert result.status == "failed"
        assert result.failed_count == 1
        assert result.metrics.mean is None
    assert read_rules(db) == ()
    if db.sqlite:
        assert "unique rules need" in _refusal(db, _typed_rule(schema, "unique", "value"))
        return
    unique = execute_rule(_prepare(db, _typed_rule(schema, "unique", "value")), source)
    assert (unique.status, unique.failed_count) == ("failed", 2)
    allowed = _typed_rule(schema, "accepted_values", "value", DqParameters(values=(FIRST,)))
    assert execute_rule(_prepare(db, allowed), source).failed_count == 1
    reference = DqParameters(reference_table="parents", reference_column="key")
    orphans = _typed_rule(schema, "referential_integrity", "value", reference)
    assert execute_rule(_prepare(db, orphans), source).failed_count == 1
    ranged = _typed_rule(schema, "range", "value", DqParameters(minimum=0))
    assert "range rules need" in _refusal(db, ranged)
    missing = _typed_rule(
        schema,
        "referential_integrity",
        "value",
        DqParameters(reference_table="absent", reference_column="key"),
    )
    assert "reference table" in _refusal(db, missing)
