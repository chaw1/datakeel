# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Catalog display names remain searchable and reproducible after event replay."""

from datakeel.core.catalog_models import CatalogObject, CatalogQuery, CatalogSnapshot
from datakeel.core.models import AssetRef
from datakeel.core.search_models import SearchQuery
from datakeel.lineage.models import GraphQuery
from datakeel.storage.catalog_projection import rebuild_catalog
from datakeel.storage.catalog_queries import get_object, read_objects
from datakeel.storage.catalog_store import publish_snapshot
from datakeel.storage.database import Database
from datakeel.storage.lineage_service import get_graph
from datakeel.storage.search import search_objects


def test_english_name_when_published_survives_search_graph_and_rebuild(db: Database) -> None:
    """One optional object field reaches current APIs without replacing the source name."""
    item = CatalogObject(
        asset_ref=AssetRef(asset_type="table", asset_id="sample/main/orders"),
        name="订单目录",
        english_name="Order directory",
    )
    publish_snapshot(db, CatalogSnapshot(scope="names", objects=(item,)))
    assert get_object(db, item.asset_ref.asset_id).name == item.name
    assert read_objects(db, CatalogQuery(search="ORDER DIRECTORY")).total == 1
    result = search_objects(db, SearchQuery(q="Order directory"))
    assert [(value.name, value.english_name) for value in result] == [
        (item.name, item.english_name)
    ]
    graph = get_graph(db, query=GraphQuery(asset_id=item.asset_ref.asset_id, include_catalog=True))
    assert graph.nodes[0].display_name == item.name
    assert graph.nodes[0].english_name == item.english_name
    assert rebuild_catalog(db).matches
    assert get_object(db, item.asset_ref.asset_id).english_name == item.english_name
