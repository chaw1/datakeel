# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""SQL assertions cannot reach side-effecting or scope-escaping database functions."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.schema import CreateSchema, DropSchema

from datakeel.core.catalog_models import SourceProperties
from datakeel.core.dq_models import DqParameters, DqRule, DqTarget
from datakeel.core.errors import ValidationError
from datakeel.quality.dq_engine import execute_rule
from datakeel.quality.dq_source import validate_assertion

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.metric_models import Scalar
    from datakeel.storage.database import Database

POSTGRES = SourceProperties(connection_url="postgresql://unused.invalid/db", dialect="postgresql")
SQLITE = SourceProperties(connection_url="sqlite:///unused.sqlite", dialect="sqlite")


def _assertion(sql: str, schema: str = "main", bindings: dict[str, Scalar] | None = None) -> DqRule:
    return DqRule(
        id="function-scope",
        name="Function scope",
        owner="quality-team",
        kind="sql_assertion",
        target=DqTarget(source_id="demo", schema_name=schema, table="shipments"),
        params=DqParameters(sql=sql, bindings=bindings or {}),
    )


@pytest.mark.parametrize(
    ("source", "sql"),
    [
        (POSTGRES, "SELECT id FROM shipments WHERE pg_sleep(20) IS NULL"),
        (POSTGRES, "SELECT id FROM shipments WHERE pg_catalog.pg_sleep(20) IS NULL"),
        (POSTGRES, 'SELECT id FROM shipments WHERE "pg_sleep"(20) IS NULL'),
        (POSTGRES, "SELECT id FROM shipments WHERE setval('audit_seq', 7) > 0"),
        (POSTGRES, "SELECT id FROM shipments WHERE nextval('audit_seq') > 0"),
        (POSTGRES, "SELECT set_config('statement_timeout', '0', false) FROM shipments"),
        (POSTGRES, "SELECT id FROM shipments WHERE pg_terminate_backend(42)"),
        (POSTGRES, "SELECT id FROM shipments WHERE pg_cancel_backend(42)"),
        (POSTGRES, "SELECT pg_advisory_lock(42) FROM shipments"),
        (
            POSTGRES,
            "SELECT id FROM shipments WHERE query_to_xml('select 1', true, true, '') IS NULL",
        ),
        (POSTGRES, "SELECT id FROM shipments WHERE length(pg_read_file('/etc/hosts')) > 0"),
        (POSTGRES, "SELECT id FROM shipments WHERE lo_import('/etc/hosts') > 0"),
        (POSTGRES, "SELECT id FROM shipments WHERE public.lower(status) = 'x'"),
        (POSTGRES, "SELECT id FROM shipments WHERE public.age(created_at) IS NULL"),
        (SQLITE, "SELECT id FROM shipments WHERE load_extension('/tmp/x') IS NULL"),
        (SQLITE, "SELECT id FROM shipments WHERE length(randomblob(900000000)) > 0"),
        (SQLITE, "SELECT id FROM shipments WHERE length(zeroblob(2000000000)) > 0"),
        (SQLITE, "SELECT id FROM shipments WHERE length(printf('%.*c', 900000000, 'x')) > 0"),
    ],
)
def test_assertion_rejects_side_effect_and_unknown_functions(
    source: SourceProperties, sql: str
) -> None:
    """Calls outside recognised read-only built-ins are refused before any connection opens."""
    with pytest.raises(ValidationError, match="functions"):
        validate_assertion(_assertion(sql), source)


@pytest.mark.parametrize(
    ("source", "sql"),
    [
        (
            POSTGRES,
            "SELECT id FROM shipments WHERE COALESCE(weight, 0) < 0 OR LOWER(TRIM(status)) = 'x'",
        ),
        (POSTGRES, "SELECT id FROM shipments WHERE EXTRACT(EPOCH FROM delivered_at) < 0"),
        (POSTGRES, "SELECT id FROM shipments WHERE date_trunc('day', created_at) > CURRENT_DATE"),
        (POSTGRES, "SELECT id FROM shipments WHERE age(delivered_at, created_at) < INTERVAL '0s'"),
        (POSTGRES, "SELECT id FROM shipments WHERE LENGTH(CAST(code AS TEXT)) <> 10"),
        (SQLITE, "SELECT id FROM shipments WHERE julianday(delivered_at) < julianday(created_at)"),
        (SQLITE, "SELECT id FROM shipments WHERE typeof(weight) <> 'real' OR ABS(weight) > 500"),
        (SQLITE, "SELECT id FROM shipments WHERE unixepoch(delivered_at) < unixepoch(created_at)"),
    ],
)
def test_assertion_keeps_common_read_only_functions(source: SourceProperties, sql: str) -> None:
    """Ordinary predicates over built-in scalar functions stay valid."""
    validate_assertion(_assertion(sql), source)


def test_rejected_function_never_reaches_the_business_source(db: Database, tmp_path: Path) -> None:
    """A rejected call yields an error verdict; on PostgreSQL another session stays alive."""
    if db.sqlite:
        path = tmp_path / "business.sqlite"
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE shipments(id INTEGER)")
            connection.execute("INSERT INTO shipments VALUES (1)")
        rule = _assertion("SELECT id FROM shipments WHERE load_extension('/tmp/absent') IS NULL")
        result = execute_rule(
            rule, SourceProperties(connection_url=f"sqlite:///{path}", dialect="sqlite")
        )
        assert result.status == "error"
        assert "functions" in result.message
        return
    schema = "dq_functions_" + uuid4().hex
    url = db.engine.url.render_as_string(hide_password=False)
    with db.engine.begin() as connection:
        connection.execute(CreateSchema(schema))
        connection.execute(
            text("SELECT set_config('search_path', :schema, true)"), {"schema": schema}
        )
        connection.execute(text("CREATE TABLE shipments(id INTEGER)"))
        connection.execute(text("INSERT INTO shipments VALUES (1)"))
    victim_engine = create_engine(url)
    try:
        with victim_engine.connect() as victim:
            pid = victim.execute(text("SELECT pg_backend_pid()")).scalar_one()
            rule = _assertion(
                "SELECT id FROM shipments WHERE pg_terminate_backend(:pid)", schema, {"pid": pid}
            )
            result = execute_rule(rule, SourceProperties(connection_url=url, dialect="postgresql"))
            assert result.status == "error"
            assert "functions" in result.message
            assert victim.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        victim_engine.dispose()
        with db.engine.begin() as connection:
            # Only this test's newly generated UUID schema is removed.
            connection.execute(DropSchema(schema, cascade=True))
