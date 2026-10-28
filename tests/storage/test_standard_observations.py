# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Lossless numeric and declared boolean observations through bounded read-only sources."""

import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from datakeel.core.catalog_identity import catalog_id
from datakeel.core.catalog_models import CatalogObject, SourceProperties
from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.models import AssetRef
from datakeel.core.standard_models import ColumnProfile, FieldStandard
from datakeel.standards.checks import check_column
from datakeel.storage.database import Database
from datakeel.storage.standard_observations import read_observations


def _table(schema: str, name: str) -> CatalogObject:
    return CatalogObject(
        asset_ref=AssetRef(asset_type="table", asset_id=catalog_id("observed", schema, name)),
        name=name,
        source_id="observed",
    )


def test_source_observations_preserve_boolean_and_postgres_exact_numeric(db: Database) -> None:
    """PostgreSQL NUMERIC retains every digit; SQLite declaration restores stored boolean intent."""
    exact = Decimal("1234567890.12345678901234567891")
    with db.engine.begin() as connection:
        schema = "main" if db.sqlite else str(connection.scalar(text("SELECT current_schema()")))
        connection.execute(
            text("CREATE TABLE observed_values(enabled BOOLEAN, amount NUMERIC(30,20))")
        )
        connection.execute(
            text("INSERT INTO observed_values VALUES (:enabled, CAST(:amount AS NUMERIC(30,20)))"),
            {"enabled": True, "amount": str(exact)},
        )
    source = SourceProperties(
        dialect="sqlite" if db.sqlite else "postgres",
        connection_url=db.engine.url.render_as_string(hide_password=False),
    )
    observed = read_observations(
        source,
        _table(schema, "observed_values"),
        (
            ColumnProfile(column_id="enabled", name="enabled", data_type="BOOLEAN"),
            ColumnProfile(column_id="amount", name="amount", data_type="NUMERIC(30,20)"),
        ),
    )
    assert observed[0].values == (True,)
    assert type(observed[0].values[0]) is bool
    if db.sqlite:
        assert isinstance(observed[1].values[0], float)
    else:
        assert observed[1].values == (exact,)
        assert isinstance(observed[1].values[0], Decimal)
        standard = FieldStandard(
            code="amount",
            name_zh="金额",
            name_en="Amount",
            description="Generated precision",
            data_type="numeric",
            precision=30,
            scale=20,
            sensitivity="restricted",
            status="active",
        )
        assert check_column(observed[1], standard).compliant
        narrower = standard.model_copy(update={"precision": 29, "scale": 19})
        assert any(
            item.rule == "precision" for item in check_column(observed[1], narrower).violations
        )


def test_sqlite_boolean_conversion_preserves_invalid_values_for_checks(tmp_path: Path) -> None:
    """Only exact zero and one values become booleans; out-of-domain integers remain violations."""
    path = tmp_path / "boolean.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE flags(enabled BOOLEAN)")
        connection.executemany("INSERT INTO flags VALUES (?)", ((0,), (1,), (2,), (None,)))
    source = SourceProperties(dialect="sqlite", connection_url=f"sqlite:///{path}")
    profile = read_observations(
        source,
        _table("main", "flags"),
        (ColumnProfile(column_id="enabled", name="enabled", data_type="BOOLEAN"),),
    )[0]
    assert profile.values == (False, True, 2, None)
    standard = FieldStandard(
        code="enabled",
        name_zh="标志",
        name_en="Enabled",
        description="Generated boolean",
        data_type="boolean",
        status="active",
    )
    violations = check_column(profile, standard).violations
    assert next(item for item in violations if item.rule == "type").count == 1


def test_unreadable_or_unsupported_source_never_creates_a_database(tmp_path: Path) -> None:
    """Invalid URLs fail with typed errors before connecting or creating source files."""
    missing = tmp_path / "absent.sqlite"
    profile = ColumnProfile(column_id="field", name="field", data_type="TEXT")
    for url in (
        f"sqlite:///{missing}",
        "sqlite:///:memory:",
        "mysql://localhost/example",
        "not-a-url",
    ):
        with pytest.raises(ValidationError):
            read_observations(
                SourceProperties(dialect="sqlite", connection_url=url),
                _table("main", "fields"),
                (profile,),
            )
    assert not missing.exists()
    assert read_observations(SourceProperties(dialect="sqlite"), _table("main", "fields"), ()) == ()


def test_source_query_failure_is_typed_without_repeating_connection_details(tmp_path: Path) -> None:
    """A missing table exposes only its error category without connection details."""
    path = tmp_path / "empty.sqlite"
    with sqlite3.connect(path):
        pass
    with pytest.raises(ExecutionError, match="Read-only standards observation failed") as failure:
        read_observations(
            SourceProperties(dialect="sqlite", connection_url=f"sqlite:///{path}"),
            _table("main", "absent"),
            (ColumnProfile(column_id="field", name="field", data_type="TEXT"),),
        )
    assert str(path) not in str(failure.value)
