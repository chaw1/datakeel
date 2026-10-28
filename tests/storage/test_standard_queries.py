# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded profiling, suggestions and redacted checks over generated registered sources."""

import sqlite3
from pathlib import Path

from datakeel.core.catalog_identity import catalog_id
from datakeel.core.catalog_models import (
    CatalogLink,
    CatalogObject,
    CatalogSnapshot,
    SourceProperties,
)
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.storage.catalog_store import publish_snapshot
from datakeel.storage.database import Database
from datakeel.storage.standard_profiles import profiles_from_snapshot
from datakeel.storage.standard_queries import list_profiles, standards_report, suggestions
from datakeel.storage.standard_store import history, list_mappings
from tests.standards_support import approved_change, install_standards


def test_profile_and_suggestions_never_confirm_or_expose_raw_values(
    db: Database, tmp_path: Path
) -> None:
    """Suggestions use observed distributions privately and leave effective mappings untouched."""
    install_standards(db, tmp_path)
    profiles = list_profiles(db)
    assert len(profiles) == 5
    assert all(item.values == () and item.row_count == 3 for item in profiles)
    customer = next(item for item in profiles if item.name == "cust_id")
    amount = next(item for item in profiles if item.name == "amount")
    assert customer.length == 8
    assert amount.precision == 6
    assert amount.scale == 2
    candidates = suggestions(db)
    assert len(candidates) == 5
    assert (
        next(item for item in candidates if item.column_id == customer.column_id)
        .candidates[0]
        .standard_code
        == "customer_id"
    )
    assert not list_mappings(db)
    assert len(history(db).revisions) == 1


def test_report_checks_only_confirmed_mappings_and_masks_samples(
    db: Database, tmp_path: Path
) -> None:
    """Coverage and violation counts come from actual observations, with no raw profile payload."""
    install_standards(db, tmp_path)
    before = standards_report(db)
    assert before.coverage.overall.mapped_columns == 0
    assert before.checks == ()
    for column, standard in (
        ("cust_id", "customer_id"),
        ("email", "email"),
        ("status", "status"),
        ("amount", "amount"),
    ):
        approved_change(
            db,
            "confirm_standard_mapping",
            JsonDocument(
                {
                    "mapping": {
                        "column_id": f"generated/main/customers/{column}",
                        "standard_code": standard,
                    }
                }
            ),
        )
    report = standards_report(db)
    assert len(report.checks) == 4
    assert all(item.row_count == 3 for item in report.checks)
    assert report.coverage.overall.coverage == 0.8
    assert report.coverage.violation_top
    assert report.coverage.sources[0].key == "generated"
    assert report.coverage.tables[0].key == "generated/main/customers"
    assert all(item.values == () for item in report.profiles)
    assert "personal@example.org" not in report.model_dump_json()
    assert standards_report(db, "absent").profiles == ()


def test_metadata_only_profiles_preserve_owner_unit_and_sensitivity(db: Database) -> None:
    """A source without a data URL remains measurable metadata without inventing value counts."""
    source = CatalogObject(
        asset_ref=AssetRef(asset_type="source", asset_id="source"),
        name="Source",
        source_id="source",
        properties=JsonDocument(SourceProperties(dialect="sqlite").model_dump(mode="json")),
    )
    table = CatalogObject(
        asset_ref=AssetRef(asset_type="table", asset_id="source/main/table"),
        name="Table",
        source_id="source",
    )
    column = CatalogObject(
        asset_ref=AssetRef(asset_type="column", asset_id="source/main/table/field"),
        name="Field",
        source_id="source",
        table_id=table.asset_ref.asset_id,
        properties=JsonDocument(
            {"data_type": "VARCHAR(12)", "unit": "kg", "sensitivity": "restricted"}
        ),
    )
    owner = CatalogObject(
        asset_ref=AssetRef(asset_type="owner", asset_id="owner"), name="Data team"
    )
    snapshot = CatalogSnapshot(
        scope="source:source",
        objects=(source, table, column, owner),
        links=(CatalogLink(source=table.asset_ref, target=owner.asset_ref, kind="owned_by"),),
    )
    publish_snapshot(db, snapshot)
    profile = profiles_from_snapshot(snapshot)[0]
    assert profile.owner == "Data team"
    assert profile.unit == "kg"
    assert profile.sensitivity == "restricted"
    assert profile.length == 12
    assert profile.row_count == 0
    assert profiles_from_snapshot(CatalogSnapshot(scope="empty")) == ()


def test_profile_identifier_quoting_and_population_cap(db: Database, tmp_path: Path) -> None:
    """Unusual identifiers remain inert and observations stay within the population cap."""
    source_path = tmp_path / "bounded.sqlite"
    with sqlite3.connect(source_path) as connection:
        connection.execute('CREATE TABLE "odd table" ("quoted""field" TEXT)')
        connection.executemany(
            'INSERT INTO "odd table" VALUES (?)', ((str(index),) for index in range(10001))
        )
    source = CatalogObject(
        asset_ref=AssetRef(asset_type="source", asset_id="s"),
        name="S",
        source_id="s",
        properties=JsonDocument(
            SourceProperties(
                dialect="sqlite", connection_url=f"sqlite:///{source_path}"
            ).model_dump(mode="json")
        ),
    )
    table = CatalogObject(
        asset_ref=AssetRef(asset_type="table", asset_id="s/main/odd%20table"),
        name="odd table",
        source_id="s",
    )
    column = CatalogObject(
        asset_ref=AssetRef(asset_type="column", asset_id="s/main/odd%20table/quoted%22field"),
        name='quoted"field',
        source_id="s",
        table_id=table.asset_ref.asset_id,
        properties=JsonDocument({"data_type": "TEXT"}),
    )
    snapshot = CatalogSnapshot(scope="source:s", objects=(source, table, column))
    profile = profiles_from_snapshot(snapshot)[0]
    assert profile.row_count == 10000
    assert len(profile.values) == 10000
    assert profile.truncated


def test_source_owner_is_inherited_for_encoded_unicode_source_identity() -> None:
    """Source ownership matches canonical IDs even when source names contain spaces or Chinese."""
    source_id = "来源 库"
    source = CatalogObject(
        asset_ref=AssetRef(asset_type="source", asset_id=catalog_id(source_id)),
        name="Generated source",
        source_id=source_id,
        properties=JsonDocument(SourceProperties(dialect="sqlite").model_dump(mode="json")),
    )
    table = CatalogObject(
        asset_ref=AssetRef(asset_type="table", asset_id=catalog_id(source_id, "main", "table")),
        name="Table",
        source_id=source_id,
    )
    column = CatalogObject(
        asset_ref=AssetRef(
            asset_type="column", asset_id=catalog_id(source_id, "main", "table", "field")
        ),
        name="Field",
        source_id=source_id,
        table_id=table.asset_ref.asset_id,
        properties=JsonDocument({"data_type": "TEXT"}),
    )
    owner = CatalogObject(asset_ref=AssetRef(asset_type="owner", asset_id="owner"), name="Steward")
    snapshot = CatalogSnapshot(
        scope=f"source:{source_id}",
        objects=(source, table, column, owner),
        links=(CatalogLink(source=source.asset_ref, target=owner.asset_ref, kind="owned_by"),),
    )
    assert profiles_from_snapshot(snapshot)[0].owner == "Steward"
