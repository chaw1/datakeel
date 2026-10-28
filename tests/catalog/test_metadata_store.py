# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Incremental source inventories merge physical objects without losing provenance."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.catalog.service import import_catalog
from datakeel.core.catalog_canonical import canonical_content
from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot
from datakeel.core.catalog_projection import project_catalog
from datakeel.core.errors import ValidationError
from datakeel.core.metadata_imports import ExternalMetadata, MetadataImportBatch, PhysicalRelation
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.storage.catalog_projection import rebuild_catalog
from datakeel.storage.catalog_queries import get_object
from datakeel.storage.catalog_store import read_snapshot
from datakeel.storage.events import all_events
from datakeel.storage.metadata_store import publish_metadata

if TYPE_CHECKING:
    from datakeel.core.catalog_models import CatalogImportRequest
    from datakeel.storage.database import Database


def _batch(db: Database, description: str = "Documented sales") -> MetadataImportBatch:
    item = get_object(db, "sample/main/sales")
    metadata = ExternalMetadata(
        system="dbt",
        unique_id="model.shop.sales",
        description=description,
        owner="owner@example.org",
        tags=("daily",),
        relation=PhysicalRelation(database="warehouse", schema_name="main", name="sales"),
    )
    item = item.model_copy(
        update={
            "properties": JsonDocument(
                {"comment": description, "integration": metadata.model_dump(mode="json")}
            )
        }
    )
    return MetadataImportBatch(
        snapshot=CatalogSnapshot(scope="metadata:dbt:sample", objects=(item,))
    )


def test_metadata_when_overlapping_identity_preserves_database_and_dbt_evidence(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """Keep exactly one physical table while independent events own its contributions."""
    import_catalog(db, source_request)
    first = publish_metadata(db, _batch(db))
    table = get_object(db, "sample/main/sales")
    assert first.new == 1
    assert table.properties.root["comment"] == "Documented sales"
    assert table.properties.root["columns"] == {
        "id": "INTEGER",
        "region_id": "INTEGER",
        "amount": "REAL",
        "day": "DATE",
    }
    assert table.properties.root["primary_key"] == ["id"]
    assert len(table.properties.root["integrations"]) == 1
    assert get_object(db, "sample").properties.root["connection_url"]
    assert get_object(db, "sample").properties.root["dialect"] == "sqlite"
    with db.session() as session:
        objects = read_snapshot(session).objects
        assert sum(item.asset_ref.asset_id == "sample/main/sales" for item in objects) == 1
        assert project_catalog(all_events(session)) == read_snapshot(session)
    assert rebuild_catalog(db).matches


def test_metadata_when_database_reimported_retains_external_description(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """A reflection replay cannot erase metadata owned by an artifact source."""
    import_catalog(db, source_request)
    publish_metadata(db, _batch(db))
    import_catalog(db, source_request)
    assert get_object(db, "sample/main/sales").properties.root["comment"] == "Documented sales"
    assert rebuild_catalog(db).matches


def test_metadata_when_replayed_changed_deleted_and_restored_reports_distinct_changes(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """Count newly missing objects once, retain tombstones, and detect restoration."""
    import_catalog(db, source_request)
    original = _batch(db)
    first = publish_metadata(db, original)
    replay = publish_metadata(db, original)
    assert (replay.new, replay.changed, replay.unchanged, replay.deleted) == (0, 0, 1, 0)
    assert replay.event_id is None
    changed = publish_metadata(db, _batch(db, "Updated owner documentation"))
    assert changed.changed == 1
    assert changed.snapshot_version == first.snapshot_version + 1
    empty = MetadataImportBatch(snapshot=CatalogSnapshot(scope=original.snapshot.scope))
    removed = publish_metadata(db, empty)
    assert removed.deleted == 1
    table = get_object(db, "sample/main/sales")
    assert table.properties.root["source_deleted"] is False
    integration = table.properties.root["integration"]
    assert isinstance(integration, dict)
    assert integration["source_deleted"] is True
    assert publish_metadata(db, empty).deleted == 0
    assert publish_metadata(db, empty).event_id is None
    restored = publish_metadata(db, original)
    assert (restored.new, restored.changed, restored.deleted) == (0, 1, 0)
    assert rebuild_catalog(db).matches


def test_metadata_when_only_source_deleted_preserves_deleted_catalog_object(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """An integration-only inventory does not physically delete removed tables."""
    import_catalog(db, source_request)
    batch = _batch(db)
    with db.session() as session:
        initial = canonical_content(read_snapshot(session))
    publish_metadata(db, batch)
    # Removing the database scope leaves the independent integration contribution.
    from datakeel.storage.catalog_store import publish_snapshot  # noqa: PLC0415

    publish_snapshot(db, CatalogSnapshot(scope="source:sample"))
    publish_metadata(db, MetadataImportBatch(snapshot=CatalogSnapshot(scope=batch.snapshot.scope)))
    table = get_object(db, "sample/main/sales")
    assert table.properties.root.get("source_deleted") is True
    assert initial.root["objects"]
    assert rebuild_catalog(db).matches


def test_metadata_when_another_kind_uses_physical_id_rejects_entire_transaction(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """A colliding orchestration node cannot overwrite a table or leave partial facts."""
    import_catalog(db, source_request)
    with db.session() as session:
        before = len(all_events(session))
    item = CatalogObject(
        asset_ref=AssetRef(asset_type="dag", asset_id="sample/main/sales"), name="Collision"
    )
    batch = MetadataImportBatch(
        snapshot=CatalogSnapshot(scope="metadata:airflow:sample", objects=(item,))
    )
    with pytest.raises(ValidationError, match="another object type"):
        publish_metadata(db, batch)
    assert get_object(db, "sample/main/sales").asset_ref.asset_type == "table"
    with db.session() as session:
        assert len(all_events(session)) == before
