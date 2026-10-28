# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Standard run transitions remain idempotent, durable and order-independent."""

from pathlib import Path

import pytest
from pydantic import ValidationError as ModelValidationError

from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot
from datakeel.core.metadata_imports import ExternalMetadata
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.core.orchestration import OpenLineageNamespace, OpenLineageRunEvent
from datakeel.storage.catalog_store import publish_snapshot, read_snapshot
from datakeel.storage.database import Database
from datakeel.storage.events import all_events
from datakeel.storage.openlineage_store import ingest_openlineage

FIXTURE = Path(__file__).parents[1] / "fixtures" / "metadata" / "openlineage.json"


def observation(
    event_type: str = "START", event_time: str = "2026-10-27T01:00:00Z", **updates: object
) -> OpenLineageRunEvent:
    """Read a generated producer event and vary only a declared observation."""
    raw = JsonDocument.model_validate_json(FIXTURE.read_text()).root
    return OpenLineageRunEvent.model_validate(
        {**raw, "eventType": event_type, "eventTime": event_time, **updates}
    )


def _metadata(db: Database, identity: str) -> ExternalMetadata:
    with db.session() as session:
        obj = next(
            item for item in read_snapshot(session).objects if item.asset_ref.asset_id == identity
        )
    return ExternalMetadata.model_validate(obj.properties["integration"])


def test_openlineage_start_complete_persists_run_records_and_schema(db: Database) -> None:
    """A successful transition enriches catalog columns and successful-output freshness."""
    started = ingest_openlineage(db, observation())
    completed = ingest_openlineage(db, observation("COMPLETE", "2026-10-27T01:05:00Z"))
    assert started.state == "START"
    assert completed.state == "COMPLETE"
    job = _metadata(db, completed.job_id)
    assert job.details["last_success"] == "2026-10-27T01:05:00+00:00"
    assert job.details["runs"][0]["state"] == "COMPLETE"
    with db.session() as session:
        snapshot = read_snapshot(session)
        column = next(obj for obj in snapshot.objects if obj.asset_ref.asset_type == "column")
        table = next(
            obj
            for obj in snapshot.objects
            if obj.table_id is None and obj.name == "orders" and obj.schema_name == "public"
        )
        facts = [event for event in all_events(session) if event.operator == "OPENLINEAGE_RUN"]
    assert len(facts) == 2
    assert column.properties["comment"] == "Order identifier"
    assert _metadata(db, table.asset_ref.asset_id).details["placeholder"] is False
    assert (
        _metadata(db, table.asset_ref.asset_id).details["last_success"]
        == "2026-10-27T01:05:00+00:00"
    )
    assert (completed.job_id, table.asset_ref.asset_id) in {
        (link.source.asset_id, link.target.asset_id) for link in snapshot.links
    }


def test_openlineage_duplicate_replay_adds_no_facts_or_projection_events(db: Database) -> None:
    """Same job/run/type is one observation even when delivered with altered metadata."""
    first = ingest_openlineage(db, observation("COMPLETE"))
    with db.session() as session:
        count = len(all_events(session))
    duplicate = ingest_openlineage(db, observation("COMPLETE", "2026-10-27T02:00:00Z"))
    with db.session() as session:
        assert len(all_events(session)) == count
    assert duplicate.inserted is False
    assert duplicate.event_id == first.event_id
    assert duplicate.occurred_at == first.occurred_at


@pytest.mark.parametrize("terminal", ["COMPLETE", "FAIL"])
def test_openlineage_delayed_start_cannot_downgrade_terminal_state(
    db: Database, terminal: str
) -> None:
    """A late START remains an observed event without changing completed run state."""
    first = ingest_openlineage(db, observation(terminal, "2026-10-27T01:05:00Z"))
    late = ingest_openlineage(db, observation("START", "2026-10-27T02:00:00Z"))
    assert late.state == terminal
    assert _metadata(db, first.job_id).details["state"] == terminal
    assert _metadata(db, first.job_id).details["last_success"] == (
        "2026-10-27T01:05:00+00:00" if terminal == "COMPLETE" else None
    )


def test_openlineage_new_run_and_late_old_event_preserve_latest_job_state(db: Database) -> None:
    """Projection orders distinct runs by observation time and keeps run histories."""
    ingest_openlineage(db, observation("START"))
    newer = ingest_openlineage(
        db, observation("FAIL", "2026-10-28T01:00:00Z", run={"runId": "another-run"})
    )
    ingest_openlineage(db, observation("COMPLETE", "2026-10-27T01:05:00Z"))
    job = _metadata(db, newer.job_id)
    assert job.details["state"] == "FAIL"
    assert len(job.details["runs"]) == 2
    assert job.details["last_success"] == "2026-10-27T01:05:00+00:00"


def test_openlineage_unknown_datasets_become_distinct_placeholders(db: Database) -> None:
    """Namespace/database boundaries prevent unrelated physical tables from collapsing."""
    dataset = {"namespace": "postgres://warehouse.example:5432/", "name": "one.public.orders"}
    event = observation(inputs=[dataset], outputs=[{**dataset, "name": "two.public.orders"}])
    ingest_openlineage(db, event)
    with db.session() as session:
        tables = [
            item for item in read_snapshot(session).objects if item.asset_ref.asset_type == "table"
        ]
    assert len({table.asset_ref.asset_id for table in tables}) == 2
    assert all(_metadata(db, table.asset_ref.asset_id).details["placeholder"] for table in tables)


def test_openlineage_explicit_namespace_mapping_merges_physical_table(db: Database) -> None:
    """A configured namespace/source mapping joins an existing reflected table identity."""
    publish_snapshot(
        db,
        CatalogSnapshot(
            scope="database:warehouse",
            objects=(
                CatalogObject(
                    asset_ref=AssetRef(asset_type="table", asset_id="warehouse/public/orders"),
                    name="orders",
                    source_id="warehouse",
                    schema_name="public",
                    properties=JsonDocument(
                        {"columns": {"order_id": "BIGINT"}, "comment": "Database table"}
                    ),
                ),
            ),
        ),
    )
    mappings = {
        "postgresql://WAREHOUSE.EXAMPLE:5432/": OpenLineageNamespace(
            source_id="warehouse", database="analytics"
        )
    }
    receipt = ingest_openlineage(db, observation("COMPLETE"), mappings)
    with db.session() as session:
        snapshot = read_snapshot(session)
    assert sum(obj.asset_ref.asset_id == "warehouse/public/orders" for obj in snapshot.objects) == 1
    assert (receipt.job_id, "warehouse/public/orders") in {
        (link.source.asset_id, link.target.asset_id) for link in snapshot.links
    }


def test_openlineage_sparse_later_event_keeps_schema_and_newer_success(db: Database) -> None:
    """Sparse events merge facets and delayed successful events cannot age freshness."""
    ingest_openlineage(db, observation("COMPLETE", "2026-10-28T01:05:00Z"))
    output = {"namespace": "postgres://warehouse.example", "name": "analytics.public.orders"}
    ingest_openlineage(
        db,
        observation("COMPLETE", "2026-10-27T01:05:00Z", run={"runId": "old-run"}, outputs=[output]),
    )
    with db.session() as session:
        snapshot = read_snapshot(session)
        table = next(
            obj
            for obj in snapshot.objects
            if obj.asset_ref.asset_type == "table" and obj.schema_name == "public"
        )
        columns = [obj for obj in snapshot.objects if obj.table_id == table.asset_ref.asset_id]
    assert len(columns) == 1
    assert (
        _metadata(db, table.asset_ref.asset_id).details["last_success"]
        == "2026-10-28T01:05:00+00:00"
    )


def test_openlineage_run_identity_includes_job_namespace(db: Database) -> None:
    """Independent producers may reuse a run ID without discarding either job."""
    first = ingest_openlineage(db, observation())
    second = ingest_openlineage(
        db, observation(job={"namespace": "airflow://other.example", "name": "daily_orders.build"})
    )
    assert first.inserted
    assert second.inserted
    assert first.event_id != second.event_id


def test_openlineage_invalid_schema_rolls_back_run_and_catalog(db: Database) -> None:
    """Malformed standard schema facets never leave a partial observation."""
    invalid = observation(
        outputs=[
            {"namespace": "warehouse", "name": "orders", "facets": {"schema": {"fields": [{}]}}}
        ]
    )
    with pytest.raises(ModelValidationError):
        ingest_openlineage(db, invalid)
    with db.session() as session:
        assert all_events(session) == []
        assert read_snapshot(session).objects == ()


def test_openlineage_late_old_schema_does_not_replace_newer_complete_schema(db: Database) -> None:
    """Dataset facet clocks resist late schema regressions independently from run state."""
    completed = observation("COMPLETE", "2026-10-27T01:05:00Z")
    ingest_openlineage(db, completed)
    output = {
        "namespace": "postgres://warehouse.example",
        "name": "analytics.public.orders",
        "facets": {"schema": {"fields": [{"name": "legacy_id", "type": "TEXT"}]}},
    }
    ingest_openlineage(db, observation("START", outputs=[output]))
    with db.session() as session:
        columns = [
            item.name
            for item in read_snapshot(session).objects
            if item.asset_ref.asset_type == "column"
        ]
    assert columns == ["order_id"]
