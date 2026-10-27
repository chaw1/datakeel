# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Detect dbt SQL and materialization changes even when the physical lineage is unchanged."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.catalog.metadata_service import import_dbt
from datakeel.core.metadata_imports import DbtImportRequest
from datakeel.core.models import JsonDocument
from datakeel.storage.catalog_projection import rebuild_catalog
from datakeel.storage.catalog_queries import get_object

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def _request(sql: str, materialized: str = "view") -> DbtImportRequest:
    return DbtImportRequest(
        source_id="shop",
        manifest=JsonDocument(
            {
                "metadata": {
                    "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v12.json"
                },
                "nodes": {
                    "seed.shop.raw": {
                        "unique_id": "seed.shop.raw",
                        "name": "raw",
                        "resource_type": "seed",
                        "columns": {"amount": {"name": "amount", "data_type": "DOUBLE"}},
                    },
                    "model.shop.orders": {
                        "unique_id": "model.shop.orders",
                        "name": "orders",
                        "resource_type": "model",
                        "config": {"materialized": materialized},
                        "compiled_code": sql,
                    },
                },
            }
        ),
    )


@pytest.mark.parametrize(
    ("new_sql", "new_materialized"),
    [
        ("SELECT amount + 2 AS amount FROM main.raw", "view"),
        ("SELECT amount + 1 AS amount FROM main.raw", "table"),
    ],
)
def test_reimport_when_only_sql_or_materialization_changes_publishes_new_definition(
    db: Database, new_sql: str, new_materialized: str
) -> None:
    """A stable field graph must not hide changed query logic or physical model behavior."""
    original = _request("SELECT amount + 1 AS amount FROM main.raw")
    first = import_dbt(db, original)
    before = get_object(db, "shop/main/orders")
    assert first.event_id is not None
    assert import_dbt(db, original).event_id is None
    changed = import_dbt(db, _request(new_sql, new_materialized))
    after = get_object(db, "shop/main/orders")
    assert changed.changed == 1
    assert changed.event_id is not None
    assert after.properties.root["sql"] == new_sql
    assert after.properties.root["is_view"] == (new_materialized == "view")
    assert after.revision == before.revision + 1
    assert import_dbt(db, _request(new_sql, new_materialized)).event_id is None
    assert rebuild_catalog(db).matches
