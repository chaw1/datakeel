# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Prove quoted SQL identities cannot select a different case-sensitive warehouse field."""

import pytest
from pydantic import JsonValue

from datakeel.catalog.importers.dbt import prepare_dbt
from datakeel.core.metadata_imports import DbtImportRequest
from datakeel.core.models import JsonDocument


def _request(sql: str, sources: dict[str, JsonValue]) -> DbtImportRequest:
    return DbtImportRequest(
        source_id="shop",
        manifest=JsonDocument(
            {
                "metadata": {
                    "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json",
                    "adapter_type": "postgres",
                },
                "nodes": {
                    "model.shop.result": {
                        "name": "result",
                        "unique_id": "model.shop.result",
                        "resource_type": "model",
                        "schema": "main",
                        "compiled_code": sql,
                    },
                    **sources,
                },
            }
        ),
    )


def _source(name: str, columns: tuple[str, ...]) -> dict[str, JsonValue]:
    return {
        "name": name,
        "unique_id": f"seed.shop.{name}",
        "resource_type": "seed",
        "schema": "main",
        "columns": {column: {"name": column, "data_type": "INTEGER"} for column in columns},
    }


def test_sql_when_quoted_fields_differ_only_by_case_derives_exact_field_edges() -> None:
    """Field and field are distinct PostgreSQL identities even when enumeration puts Field first."""
    batch = prepare_dbt(
        _request(
            'SELECT "Field" AS upper_value, "field" AS lower_value FROM main.raw',
            {"seed.shop.raw": _source("raw", ("Field", "field"))},
        )
    )
    assert not batch.parse_failures
    edges = {
        (link.source.asset_id, link.target.asset_id)
        for link in batch.snapshot.links
        if link.kind == "derived"
    }
    assert edges == {
        ("shop/main/raw/Field", "shop/main/result/upper_value"),
        ("shop/main/raw/field", "shop/main/result/lower_value"),
    }


def test_sql_when_quoted_output_names_differ_by_case_preserves_both_outputs() -> None:
    """Keep exact projected names instead of collapsing both selected fields into field."""
    batch = prepare_dbt(
        _request(
            'SELECT "Field", "field" FROM main.raw',
            {"seed.shop.raw": _source("raw", ("Field", "field"))},
        )
    )
    assert not batch.parse_failures
    edges = {
        (link.source.asset_id, link.target.asset_id)
        for link in batch.snapshot.links
        if link.kind == "derived"
    }
    assert edges == {
        ("shop/main/raw/Field", "shop/main/result/Field"),
        ("shop/main/raw/field", "shop/main/result/field"),
    }


def test_sql_when_quoted_tables_differ_only_by_case_derives_exact_table_edge() -> None:
    """A lowercase physical table cannot be replaced by the first case-folded table match."""
    batch = prepare_dbt(
        _request(
            'SELECT value AS result FROM main."raw"',
            {
                "seed.shop.Raw": _source("Raw", ("value",)),
                "seed.shop.raw": _source("raw", ("value",)),
            },
        )
    )
    assert not batch.parse_failures
    assert {
        (link.source.asset_id, link.target.asset_id)
        for link in batch.snapshot.links
        if link.kind == "derived"
    } == {("shop/main/raw/value", "shop/main/result/result")}


def test_sql_when_casefold_match_is_ambiguous_reports_failure_instead_of_guessing() -> None:
    """An absent quoted FIELD does not authorize choosing between registered Field and field."""
    batch = prepare_dbt(
        _request(
            'SELECT "FIELD" AS result FROM main.raw',
            {
                "seed.shop.raw": _source("raw", ("Field", "field")),
            },
        )
    )
    assert len(batch.parse_failures) == 1
    assert not any(link.kind == "derived" for link in batch.snapshot.links)


@pytest.mark.parametrize("registered", ["Field", "field"])
def test_sql_when_casefold_match_is_unique_keeps_existing_compatibility(registered: str) -> None:
    """Retain the existing unique-case-fold fallback for dialect-normalized field names."""
    batch = prepare_dbt(
        _request(
            'SELECT "FIELD" AS result FROM main.raw',
            {
                "seed.shop.raw": _source("raw", (registered,)),
            },
        )
    )
    assert not batch.parse_failures
    assert any(
        link.source.asset_id == f"shop/main/raw/{registered}" and link.kind == "derived"
        for link in batch.snapshot.links
    )
