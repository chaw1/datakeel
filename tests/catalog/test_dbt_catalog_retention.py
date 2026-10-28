# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Omitting catalog.json is missing column information, never evidence of dropped columns."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from datakeel.catalog.metadata_service import import_dbt
from datakeel.core.metadata_imports import DbtImportRequest
from datakeel.core.models import JsonDocument
from datakeel.storage.catalog_reads import read_snapshot

if TYPE_CHECKING:
    from datakeel.core.catalog_models import CatalogSnapshot
    from datakeel.storage.database import Database

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "dbt"


def _artifact(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / f"{name}.json").read_text())


def _request(catalog: dict[str, Any] | None) -> DbtImportRequest:
    return DbtImportRequest(
        source_id="shop",
        manifest=JsonDocument(_artifact("manifest")),
        catalog=JsonDocument(catalog) if catalog is not None else None,
        run_results=JsonDocument(_artifact("run_results")),
    )


def _state(db: Database) -> tuple[dict[str, Any], set[tuple[str, str]]]:
    with db.session() as session:
        snapshot: CatalogSnapshot = read_snapshot(session)
    columns = {
        item.asset_ref.asset_id: (
            item.properties.root.get("data_type"),
            item.properties.root.get("source_deleted"),
        )
        for item in snapshot.objects
        if item.asset_ref.asset_type == "column"
    }
    derived = {
        (link.source.asset_id, link.target.asset_id)
        for link in snapshot.links
        if link.kind == "derived"
    }
    return columns, derived


def test_dbt_reimport_without_catalog_keeps_previous_columns_types_and_lineage(
    db: Database,
) -> None:
    """Reimporting the same project without catalog.json deletes and changes nothing."""
    import_dbt(db, _request(_artifact("catalog")))
    before = _state(db)
    report = import_dbt(db, _request(None))
    assert (report.new, report.changed, report.deleted) == (0, 0, 0)
    assert report.event_id is None
    assert report.retained_columns == 17
    note = (
        "catalog.json was not provided; kept 17 columns from the previous import "
        "instead of marking them source-deleted"
    )
    assert report.notes == (note,)
    assert _state(db) == before
    assert before[0]["shop/history/order_history/dbt_scd_id"] == ("VARCHAR", None)


def test_dbt_only_an_import_with_catalog_marks_a_missing_column_deleted(db: Database) -> None:
    """A supplied catalog without a column is the evidence that the column was dropped."""
    import_dbt(db, _request(_artifact("catalog")))
    import_dbt(db, _request(None))
    catalog = _artifact("catalog")
    del catalog["nodes"]["snapshot.p22_shop.order_history"]["columns"]["dbt_scd_id"]
    report = import_dbt(db, _request(catalog))
    columns, _derived = _state(db)
    assert report.deleted == 1
    assert report.retained_columns == 0
    assert report.notes == ()
    assert columns["shop/history/order_history/dbt_scd_id"][1] is True
    assert columns["shop/history/order_history/amount"][1] is None


def test_dbt_first_import_without_catalog_says_no_columns_were_kept(db: Database) -> None:
    """With nothing to carry over, the summary still explains the missing artifact."""
    report = import_dbt(db, _request(None))
    assert report.retained_columns == 0
    assert report.notes == (
        "catalog.json was not provided and no previous import had reflected columns",
    )
