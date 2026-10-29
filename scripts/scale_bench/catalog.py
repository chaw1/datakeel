# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Publish a deterministic metadata catalog and query its production interfaces."""

from functools import partial

from datakeel.core.catalog_models import (
    CatalogLink,
    CatalogObject,
    CatalogQuery,
    CatalogSnapshot,
)
from datakeel.core.models import AssetRef
from datakeel.lineage.models import GraphQuery
from datakeel.storage.catalog_queries import get_object, read_objects
from datakeel.storage.catalog_store import publish_snapshot
from datakeel.storage.lineage_service import get_graph
from scripts.scale_bench.common import check_resources, elapsed, fingerprint, measure
from scripts.scale_bench.models import Context, ScenarioResult


def snapshot(context: Context) -> CatalogSnapshot:
    """Create bounded-degree derivations plus explicit source/table containment."""
    count = context.scale.tables
    source = AssetRef(asset_type="source", asset_id=f"scale-{context.config.seed}")
    tables = tuple(
        AssetRef(asset_type="table", asset_id=f"{source.asset_id}/main/table_{index:06d}")
        for index in range(count)
    )
    objects = [CatalogObject(asset_ref=source, name="Synthetic catalog")]
    objects.extend(
        CatalogObject(asset_ref=ref, name=f"table_{index:06d}", source_id=source.asset_id)
        for index, ref in enumerate(tables)
    )
    links = [CatalogLink(source=source, target=ref, kind="contains") for ref in tables]
    columns: list[AssetRef] = []
    for index in range(context.scale.columns):
        table = tables[index % count]
        ref = AssetRef(
            asset_type="column", asset_id=f"{table.asset_id}/column_{index // count:03d}"
        )
        columns.append(ref)
        objects.append(
            CatalogObject(
                asset_ref=ref,
                name=f"column_{index // count:03d}",
                source_id=source.asset_id,
                table_id=table.asset_id,
            )
        )
        links.append(CatalogLink(source=table, target=ref, kind="contains"))
    links.extend(
        CatalogLink(
            source=columns[index % len(columns)],
            target=columns[(index + 1) % len(columns)],
            kind="derived",
        )
        for index in range(context.scale.edges)
    )
    return CatalogSnapshot(scope="scale-catalog", objects=tuple(objects), links=tuple(links))


def _checked_graph(context: Context, query: GraphQuery) -> None:
    result = get_graph(context.db, query=query)
    columns = sum(node.asset_type == "column" for node in result.nodes)
    if result.truncated or columns < query.depth + 1:
        message = "Depth-five catalog query omitted its generated derivation chain"
        raise AssertionError(message)


def run(context: Context) -> ScenarioResult:
    """Measure real snapshot publication, paged search, exact reads and depth-five BFS."""
    objects = context.scale.tables + context.scale.columns + 1
    edges = context.scale.tables + context.scale.columns + context.scale.edges
    reserve = objects * 4096 + edges * 2048
    check_resources(context, reserve_bytes=reserve)
    fixture = snapshot(context)
    digest = fingerprint(
        {
            "seed": context.config.seed,
            "tables": context.scale.tables,
            "columns": context.scale.columns,
            "edges": context.scale.edges,
            "fixture_version": 1,
        }
    )
    check_resources(context, reserve_bytes=reserve)
    report, seconds = elapsed(lambda: publish_snapshot(context.db, fixture))
    check_resources(context)
    if report.object_count != len(fixture.objects) or report.link_count != len(fixture.links):
        message = "Catalog publication did not preserve every generated object and edge"
        raise AssertionError(message)
    focus_index = min(context.scale.columns - 1, context.scale.edges // 2)
    focus = fixture.objects[context.scale.tables + 1 + focus_index].asset_ref.asset_id
    query = CatalogQuery(kind="table", search="table_000", limit=50)
    repeated = context.config.repeats
    latencies = {
        "search": measure(lambda: read_objects(context.db, query), repeated),
        "object": measure(lambda: get_object(context.db, focus), repeated),
    }
    for direction in ("upstream", "downstream"):
        options = GraphQuery(asset=focus, direction=direction, depth=5, include_catalog=True)
        latencies[direction] = measure(partial(_checked_graph, context, options), repeated)
    return ScenarioResult(
        scenario="B3",
        counts={
            "tables": context.scale.tables,
            "columns": context.scale.columns,
            "lineage_edges": context.scale.edges,
            "projection_edges": report.link_count,
        },
        metrics={"import_seconds": seconds},
        latencies=latencies,
        fixture_sha256=digest,
        notes=("Catalog snapshot publication is the production import persistence boundary.",),
    )
