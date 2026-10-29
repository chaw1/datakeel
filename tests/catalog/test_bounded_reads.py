# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Catalog pages and bounded graphs preserve Unicode matching and full projection results."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from datakeel.core.catalog_models import (
    CatalogLink,
    CatalogObject,
    CatalogQuery,
    CatalogSnapshot,
)
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.core.search_models import SearchQuery
from datakeel.lineage.models import GraphOverlay, GraphQuery
from datakeel.lineage.service import graph
from datakeel.storage.catalog_pages import read_page
from datakeel.storage.catalog_queries import get_object, read_objects
from datakeel.storage.catalog_reads import read_snapshot
from datakeel.storage.catalog_rows import CatalogObjectRow
from datakeel.storage.catalog_store import publish_snapshot
from datakeel.storage.events import all_events
from datakeel.storage.lineage_service import get_graph
from datakeel.storage.search import search_objects

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def _fixture() -> CatalogSnapshot:
    refs = tuple(AssetRef(asset_type="table", asset_id=f"table-{index:03d}") for index in range(30))
    return CatalogSnapshot(
        scope="bounded-test",
        objects=tuple(
            CatalogObject(asset_ref=ref, name=f"Table {index}", source_id="source")
            for index, ref in enumerate(refs)
        ),
        links=tuple(
            CatalogLink(source=refs[index], target=refs[index + offset], kind="derived")
            for index in range(len(refs))
            for offset in (1, 2)
            if index + offset < len(refs)
        ),
    )


def test_pages_when_search_uses_unicode_casefold_keeps_literal_wildcards(db: Database) -> None:
    """Retain Python casefold behavior and literal percent/underscore across both stacks."""
    snapshot = CatalogSnapshot(
        scope="unicode",
        objects=tuple(
            CatalogObject(
                asset_ref=AssetRef(asset_type="table", asset_id=f"table-{index}"),
                name=name,
                english_name=english,
            )
            for index, (name, english) in enumerate(
                (("Straße", "Sales 100%"), ("STRASSE", "sales_a"), ("Other", "salesXa"))
            )
        ),
    )
    publish_snapshot(db, snapshot)
    with db.session() as session:
        result = read_page(session, CatalogQuery(search="strasse", offset=1, limit=1))
        assert result.total == 2
        assert result.items[0].name == "STRASSE"
        assert read_page(session, CatalogQuery(search="100%")).total == 1
        assert read_page(session, CatalogQuery(search="sales_a")).total == 1


def test_pages_when_filters_paginate_keeps_total_and_order(db: Database) -> None:
    """Read stable source-scoped pages without loading unrelated relationships."""
    fixture = _fixture()
    publish_snapshot(db, fixture)
    result = read_objects(db, CatalogQuery(kind="table", source_id="source", offset=7, limit=3))
    assert result.total == 30
    assert tuple(item.asset_ref.asset_id for item in result.items) == (
        "table-007",
        "table-008",
        "table-009",
    )
    assert get_object(db, "table-007").name == "Table 7"


@pytest.mark.parametrize("metadata", ["note\0value", "note\ud800value"])
def test_catalog_scalar_reads_preserve_opaque_control_character_properties(
    db: Database, metadata: str
) -> None:
    """Unrelated JSON properties cannot break public name or source projections."""
    objects = tuple(
        CatalogObject(
            asset_ref=AssetRef(asset_type="table", asset_id=f"table-{index}"),
            name="Straße" if index < 2 else "Other",
            english_name=f"Sales {index}",
            source_id="source" if index != 1 else "other-source",
            properties=JsonDocument({"note": metadata}),
        )
        for index in range(3)
    )
    with db.session() as session:
        session.add_all(
            CatalogObjectRow(
                asset_id=item.asset_ref.asset_id,
                scope="escaped-properties",
                kind="table",
                payload=item.model_dump(mode="json"),
            )
            for item in objects
        )
        session.commit()
    page = read_objects(db, CatalogQuery(search="strasse", offset=1, limit=1))
    assert page.total == 2
    assert page.items == (objects[1],)
    for search in (None, "sales"):
        scoped = read_objects(
            db, CatalogQuery(source_id="source", search=search, offset=1, limit=1)
        )
        assert scoped.total == 2
        assert scoped.items == (objects[2],)
    assert [item.id for item in search_objects(db, SearchQuery(q="sales"))] == [
        "table-2",
        "table-0",
        "table-1",
    ]
    assert search_objects(db, SearchQuery(q="note")) == []


def test_graph_when_unfocused_catalog_keeps_complete_projection(db: Database) -> None:
    """Retain the unscoped catalog view when there is no BFS focus."""
    publish_snapshot(db, _fixture())
    result = get_graph(db, query=GraphQuery(include_catalog=True))
    assert len(result.nodes) == 30
    assert len(result.edges) == 57
    assert not result.truncated


def test_graph_when_link_ref_kind_is_stale_orders_by_current_object_kind(db: Database) -> None:
    """Current object projection overrides historical link labels before applying the bound."""
    root = AssetRef(asset_type="table", asset_id="root")
    column = AssetRef(asset_type="column", asset_id="z-column")
    table = AssetRef(asset_type="table", asset_id="a-table")
    fixture = CatalogSnapshot(
        scope="stale-ref",
        objects=tuple(
            CatalogObject(asset_ref=ref, name=ref.asset_id) for ref in (root, column, table)
        ),
        links=(
            CatalogLink(
                source=root,
                target=column.model_copy(update={"asset_type": "table"}),
                kind="derived",
            ),
            CatalogLink(
                source=root,
                target=table.model_copy(update={"asset_type": "column"}),
                kind="derived",
            ),
        ),
    )
    publish_snapshot(db, fixture)
    result = get_graph(
        db,
        query=GraphQuery(asset="root", direction="downstream", max_nodes=2, include_catalog=True),
    )
    assert {node.asset_id for node in result.nodes} == {"root", "z-column"}
    assert result.truncated


def test_graph_when_ids_contain_unicode_or_punctuation_uses_python_order(db: Database) -> None:
    """Database locale must not alter which equally typed neighbors fit the graph bound."""
    root = AssetRef(asset_type="table", asset_id="root")
    children = tuple(
        AssetRef(asset_type="table", asset_id=identity) for identity in ("Á", "a_", "a!", "Z")
    )
    publish_snapshot(
        db,
        CatalogSnapshot(
            scope="graph-order",
            objects=tuple(
                CatalogObject(asset_ref=ref, name=ref.asset_id) for ref in (root, *children)
            ),
            links=tuple(CatalogLink(source=root, target=ref, kind="derived") for ref in children),
        ),
    )
    result = get_graph(
        db,
        query=GraphQuery(asset="root", direction="downstream", max_nodes=3, include_catalog=True),
    )
    assert {node.asset_id for node in result.nodes} == {"root", "Z", "a!"}


def test_graph_when_external_ref_kinds_disagree_keeps_unique_neighbor_bound(db: Database) -> None:
    """Links may reference objects outside this snapshot without consuming the bound twice."""
    root = AssetRef(asset_type="table", asset_id="root")
    other = AssetRef(asset_type="table", asset_id="z-other")
    external = AssetRef(asset_type="column", asset_id="external")
    publish_snapshot(
        db,
        CatalogSnapshot(
            scope="external-ref",
            objects=tuple(CatalogObject(asset_ref=ref, name=ref.asset_id) for ref in (root, other)),
            links=(
                CatalogLink(source=root, target=external, kind="contains"),
                CatalogLink(
                    source=root,
                    target=external.model_copy(update={"asset_type": "table"}),
                    kind="derived",
                ),
                CatalogLink(source=root, target=other, kind="derived"),
            ),
        ),
    )
    query = GraphQuery(asset="root", direction="downstream", max_nodes=3, include_catalog=True)
    with db.session() as session:
        expected = graph(
            all_events(session),
            "root",
            "downstream",
            20,
            GraphOverlay(catalog=read_snapshot(session)),
            3,
        )
    assert get_graph(db, query=query) == expected
    assert not expected.truncated


@pytest.mark.parametrize("direction", ["both", "upstream", "downstream"])
@pytest.mark.parametrize("depth", [0, 1, 5])
@pytest.mark.parametrize("limit", [1, 8, 200])
def test_graph_when_catalog_focused_matches_full_projection(
    db: Database, direction: str, depth: int, limit: int
) -> None:
    """Preserve selected node order, induced edges, truncation and complete event history."""
    fixture = _fixture()
    publish_snapshot(db, fixture)
    publish_snapshot(
        db,
        fixture.model_copy(
            update={
                "objects": tuple(
                    item.model_copy(update={"name": "Renamed"}) for item in fixture.objects
                )
            }
        ),
    )
    query = GraphQuery.model_validate(
        {
            "asset": "table-010",
            "direction": direction,
            "depth": depth,
            "max_nodes": limit,
            "include_catalog": True,
        }
    )
    with db.session() as session:
        expected = graph(
            all_events(session),
            query.asset,
            direction,
            depth,
            GraphOverlay(catalog=read_snapshot(session)),
            limit,
        )
    assert get_graph(db, query=query) == expected
