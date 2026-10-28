# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real dbt artifacts and database reflection share physical catalog identities."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from datakeel.catalog.metadata_service import import_dbt
from datakeel.catalog.service import import_catalog
from datakeel.core.catalog_models import CatalogImportRequest, CatalogQuery
from datakeel.core.metadata_imports import DbtImportRequest, ExternalMetadata
from datakeel.core.models import JsonDocument
from datakeel.storage.catalog_projection import rebuild_catalog
from datakeel.storage.catalog_queries import get_object, read_objects

if TYPE_CHECKING:
    from datakeel.storage.database import Database

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "dbt"


@pytest.mark.parametrize("database_first", [True, False])
def test_real_dbt_and_database_imports_merge_in_either_order(
    db: Database, tmp_path: Path, *, database_first: bool
) -> None:
    """Import both adapters and preserve one table, physical constraints and dbt descriptions."""
    path = tmp_path / "warehouse.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            "CREATE TABLE raw_orders(order_id INTEGER PRIMARY KEY, amount DOUBLE, ordered_at DATE);"
            'CREATE VIEW "Orders Daily" AS SELECT order_id,amount,ordered_at FROM raw_orders;'
        )
    physical = CatalogImportRequest(
        source_id="shop", name="Warehouse", connection_url=f"sqlite:///{path}"
    )
    artifacts = DbtImportRequest(
        source_id="shop",
        manifest=JsonDocument.model_validate_json((_FIXTURES / "manifest.json").read_text()),
        catalog=JsonDocument.model_validate_json((_FIXTURES / "catalog.json").read_text()),
        run_results=JsonDocument.model_validate_json((_FIXTURES / "run_results.json").read_text()),
    )
    if database_first:
        import_catalog(db, physical)
        report = import_dbt(db, artifacts)
    else:
        report = import_dbt(db, artifacts)
        import_catalog(db, physical)
    assert report.failed_sql_count == 0
    tables = read_objects(db, CatalogQuery(kind="table", source_id="shop")).items
    assert sum(item.asset_ref.asset_id == "shop/main/Orders%20Daily" for item in tables) == 1
    table = get_object(db, "shop/main/Orders%20Daily")
    metadata = ExternalMetadata.model_validate(table.properties.root["integration"])
    assert metadata.owner == "Finance"
    assert table.properties.root["comment"] == "Daily fictional orders"
    assert get_object(db, "shop/main/raw_orders").properties.root["primary_key"] == ["order_id"]
    source = get_object(db, "shop")
    assert source.properties.root["connection_url"] == physical.connection_url
    assert source.properties.root["dialect"] == "sqlite"
    assert import_catalog(db, physical).event_id is None
    assert (
        ExternalMetadata.model_validate(
            get_object(db, table.asset_ref.asset_id).properties.root["integration"]
        ).owner
        == "Finance"
    )
    assert rebuild_catalog(db).matches
