# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Query a million-edge persisted catalog projection with bounded-degree fixtures."""

from itertools import batched

from sqlalchemy import insert

from datakeel.core.catalog_models import CatalogLink, CatalogObject
from datakeel.core.models import AssetRef, LineageEvent
from datakeel.lineage.models import GraphQuery
from datakeel.storage.catalog_rows import CatalogEdgeRow, CatalogObjectRow
from datakeel.storage.events import append_event
from datakeel.storage.lineage_service import get_graph
from scripts.scale_bench.common import check_resources, elapsed, fingerprint, measure
from scripts.scale_bench.models import Context, ScenarioResult

DEGREE = 10
BATCH = 1000


def _ref(index: int) -> AssetRef:
    return AssetRef(asset_type="column", asset_id=f"graph/column_{index:07d}")


def _seed(context: Context) -> tuple[str, int]:
    count = max(DEGREE + 1, context.scale.graph_edges // DEGREE)
    event = LineageEvent(
        event_id="scale-graph-fixture",
        idempotency_key="scale-graph-fixture",
        operator="scale.graph",
        outputs=[_ref(0)],
        params={"seed": context.config.seed, "edges": context.scale.graph_edges},
    )
    with context.db.session() as session:
        append_event(session, event)
        for chunk in batched(range(count), BATCH):
            session.execute(
                insert(CatalogObjectRow).values(
                    [
                        {
                            "asset_id": _ref(index).asset_id,
                            "scope": "scale-graph",
                            "kind": "column",
                            "payload": CatalogObject(
                                asset_ref=_ref(index), name=f"column_{index:07d}"
                            ).model_dump(mode="json"),
                        }
                        for index in chunk
                    ]
                ),
            )
        for chunk in batched(range(context.scale.graph_edges), BATCH):
            session.execute(insert(CatalogEdgeRow).values([_edge(index, count) for index in chunk]))
            if chunk[0] % 10_000 == 0:
                check_resources(context)
        session.commit()
    check_resources(context)
    return _ref(0).asset_id, count


def _edge(index: int, count: int) -> dict[str, object]:
    source = _ref((index // DEGREE) % count)
    target = _ref((index // DEGREE + index % DEGREE + 1) % count)
    link = CatalogLink(
        source=source, target=target, kind="derived", producer_event_id="scale-graph-fixture"
    )
    return {
        "id": f"graph-edge-{index:09d}",
        "scope": "scale-graph",
        "kind": "derived",
        "source_id": source.asset_id,
        "target_id": target.asset_id,
        "producer_event_id": "scale-graph-fixture",
        "payload": link.model_dump(mode="json"),
    }


def run(context: Context) -> ScenarioResult:
    """Seed a query-only derived fixture, then call the production graph reader."""
    reserve = context.scale.graph_edges * 2048 + (context.scale.graph_edges // DEGREE) * 4096
    check_resources(context, reserve_bytes=reserve)
    (focus, nodes), seconds = elapsed(lambda: _seed(context))
    options = GraphQuery(asset=focus, depth=5, direction="downstream", include_catalog=True)
    result = get_graph(context.db, query=options)
    if len(result.nodes) != min(nodes, DEGREE * options.depth + 1) or result.truncated:
        message = "Graph query omitted part of the deterministic depth-five neighborhood"
        raise AssertionError(message)
    return ScenarioResult(
        scenario="B7",
        counts={
            "edges": context.scale.graph_edges,
            "nodes": nodes,
            "returned_nodes": len(result.nodes),
            "returned_edges": len(result.edges),
        },
        metrics={"fixture_seconds": seconds, "truncated": result.truncated},
        latencies={
            "graph": measure(lambda: get_graph(context.db, query=options), context.config.repeats)
        },
        fixture_sha256=fingerprint(
            {"seed": context.config.seed, "edges": context.scale.graph_edges, "degree": DEGREE}
        ),
        notes=(
            "Graph type: persisted catalog projection; fixture rows are batch seeded.",
            "This measures bounded production graph queries, not graph ingestion or generic KG.",
        ),
    )
