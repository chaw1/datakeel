# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Idempotent append-only snapshots, pagination, and explicit metadata graph behavior."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.catalog.service import import_catalog, prepare_import
from datakeel.core.catalog_models import (
    CatalogImportRequest,
    CatalogLink,
    CatalogObject,
    CatalogQuery,
    CatalogSnapshot,
)
from datakeel.core.catalog_projection import project_catalog
from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.models import AssetRef, JsonDocument, LineageEvent
from datakeel.lineage.models import GraphQuery
from datakeel.ontology.models import ObjectSet
from datakeel.storage.catalog_queries import get_object, impact, neighbors, read_objects
from datakeel.storage.catalog_store import publish_snapshot, read_snapshot
from datakeel.storage.events import all_events
from datakeel.storage.lineage_service import get_graph
from datakeel.storage.object_queries import evaluate

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_import_when_identical_replay_keeps_event_count(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """Repeat reflection through new source connections and prove no duplicate event."""
    first = import_catalog(db, source_request)
    again = import_catalog(db, source_request)
    with db.session() as session:
        assert len(all_events(session)) == 1
    assert first.new == first.object_count
    assert again.event_id is None
    assert again.unchanged == first.object_count
    assert again.snapshot_version == 1


def test_snapshot_when_changed_and_restored_keeps_immutable_history(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """Treat a rollback as a new version and recover current state from events alone."""
    snapshot, _ = prepare_import(source_request)
    first = publish_snapshot(db, snapshot)
    changed = snapshot.model_copy(
        update={
            "objects": (
                snapshot.objects[0].model_copy(update={"name": "Changed"}),
                *snapshot.objects[1:],
            )
        }
    )
    second = publish_snapshot(db, changed)
    assert second.changed == 1
    assert get_object(db, "sample").revision == 2
    third = publish_snapshot(db, snapshot)
    assert third.snapshot_version == 3
    assert get_object(db, "sample").revision == 3
    with db.session() as session:
        events = all_events(session)
        assert len(events) == 3
        assert project_catalog(events) == read_snapshot(session)
        assert events[0].event_id == first.event_id


def test_snapshot_when_identity_duplicates_rejects_before_event(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """Prevent ambiguous identity ownership within a version."""
    snapshot, _ = prepare_import(source_request)
    with pytest.raises(ValidationError, match="unique"):
        publish_snapshot(db, snapshot.model_copy(update={"objects": snapshot.objects * 2}))


def test_queries_when_filters_and_pages_return_stable_bounded_result(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """Apply source, containment, and text filters before page limits."""
    import_catalog(db, source_request)
    result = read_objects(
        db,
        CatalogQuery(
            kind="column",
            source_id="sample",
            parent_id="sample/main/sales",
            search="a",
            limit=1,
            offset=1,
        ),
    )
    assert result.total == 2
    assert len(result.items) == 1
    assert read_objects(db).total > result.total
    assert read_objects(db, CatalogQuery(source_id="absent")).total == 0
    assert neighbors(db, "sample/main/sales").links
    assert not neighbors(db, "absent").objects
    with pytest.raises(NotFoundError):
        get_object(db, "absent")
    with pytest.raises(NotFoundError):
        impact(db, "absent")


def _semantic_objects() -> CatalogSnapshot:
    metric = CatalogObject(
        asset_ref=AssetRef(asset_type="metric", asset_id="metric:sales"),
        name="Sales",
        properties=JsonDocument({"version": 1}),
    )
    term = CatalogObject(
        asset_ref=AssetRef(asset_type="term", asset_id="term:sales"), name="Retail"
    )
    owner = CatalogObject(
        asset_ref=AssetRef(asset_type="owner", asset_id="owner:sales"), name="Owner"
    )
    column = AssetRef(asset_type="column", asset_id="sample/main/sales/amount")
    return CatalogSnapshot(
        scope="semantic-layer",
        objects=(metric, term, owner),
        links=(
            CatalogLink(source=metric.asset_ref, target=column, kind="measures"),
            CatalogLink(source=term.asset_ref, target=metric.asset_ref, kind="means"),
            CatalogLink(source=metric.asset_ref, target=owner.asset_ref, kind="owned_by"),
        ),
    )


def test_graph_when_metric_focused_is_bounded_and_impact_reaches_dependents(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """Traverse field, containing table, metric, and term without fabricated cross edges."""
    import_catalog(db, source_request)
    publish_snapshot(db, _semantic_objects(), operator="METRIC_CHANGE")
    result = impact(db, "sample/main/sales/amount")
    assert {"column", "table", "metric", "term"} <= {
        item.asset_ref.asset_type for item in result.objects
    }
    assert "owner" not in {item.asset_ref.asset_type for item in result.objects}
    graph = get_graph(
        db, query=GraphQuery(asset_id="metric:sales", hops=2, max_nodes=30, include_catalog=True)
    )
    assert {"metric", "column", "table"} <= {node.asset_type for node in graph.nodes}
    assert all(edge.kind == "catalog" for edge in graph.edges)
    assert all(edge.event_id for edge in graph.edges)
    assert impact(db, "sample/main/sales/amount", max_nodes=2).truncated
    assert get_graph(
        db, query=GraphQuery(asset_id="metric:sales", hops=2, max_nodes=1, include_catalog=True)
    ).truncated


def test_object_set_when_metadata_kind_freezes_event_projection(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """Make new metadata kinds available through existing frozen asset selection."""
    import_catalog(db, source_request)
    with pytest.raises(ValueError, match="frozen asset selections"):
        evaluate(db, ObjectSet(object_type="table"))


def test_projection_when_scope_replaced_removes_old_links_but_keeps_events(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """Current scope snapshots supersede old memberships rather than accumulating ghosts."""
    import_catalog(db, source_request)
    publish_snapshot(db, CatalogSnapshot(scope="source:sample"))
    assert read_objects(db).total == 0
    assert not get_graph(
        db, query=GraphQuery(asset_id="sample/main/sales", hops=2, include_catalog=True)
    ).nodes
    with db.session() as session:
        assert len(all_events(session)) == 2


def test_projection_when_failed_snapshot_event_ignores_payload() -> None:
    """Only successful metadata publication may contribute current objects."""
    failed = LineageEvent(
        idempotency_key="failed",
        operator="CATALOG_IMPORT",
        run_state="FAILED",
        params={"catalog_snapshot": _semantic_objects().model_dump(mode="json")},
    )
    assert not project_catalog([failed]).objects


def test_snapshot_when_only_ordinal_changes_remains_unchanged(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """Exclude column enumeration order from both object and snapshot change identities."""
    snapshot, _ = prepare_import(source_request)
    publish_snapshot(db, snapshot)
    shuffled = snapshot.model_copy(
        update={
            "objects": tuple(
                item.model_copy(
                    update={"properties": JsonDocument({**item.properties.root, "ordinal": 99})}
                )
                if item.asset_ref.asset_type == "column"
                else item
                for item in reversed(snapshot.objects)
            ),
            "links": tuple(reversed(snapshot.links)),
        }
    )
    report = publish_snapshot(db, shuffled)
    assert report.event_id is None
    assert report.unchanged == len(snapshot.objects)


def test_impact_when_long_chain_stops_at_three_hops_and_slices_forward(db: Database) -> None:
    """Honor fixed impact directions and exclude dependencies beyond the bounded horizon."""
    objects = tuple(
        CatalogObject(asset_ref=AssetRef(asset_type=kind, asset_id=identity), name=identity)
        for kind, identity in (
            ("column", "c0"),
            ("column", "c1"),
            ("column", "c2"),
            ("column", "c3"),
            ("column", "c4"),
            ("metric", "m"),
            ("dimension", "d"),
            ("term", "t"),
        )
    )
    refs = {item.name: item.asset_ref for item in objects}
    links = tuple(
        CatalogLink.model_validate({"source": refs[source], "target": refs[target], "kind": kind})
        for source, target, kind in (
            ("c0", "c1", "derived"),
            ("c1", "c2", "derived"),
            ("c2", "c3", "derived"),
            ("c3", "c4", "derived"),
            ("m", "c0", "measures"),
            ("m", "d", "sliced_by"),
            ("t", "d", "means"),
        )
    )
    publish_snapshot(db, CatalogSnapshot(scope="impact-test", objects=objects, links=links))
    result = impact(db, "c0")
    assert {item.name for item in result.objects} == {"c0", "c1", "c2", "c3", "m", "d", "t"}
    assert [item.asset_ref.asset_type for item in result.objects] == sorted(
        item.asset_ref.asset_type for item in result.objects
    )
    assert {item.name for item in impact(db, "d").objects} == {"d", "t"}
