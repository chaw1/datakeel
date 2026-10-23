# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Catalog lineage is an explicit bounded projection on the existing graph endpoint."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pytest

from datakeel.actions import service as actions
from datakeel.actions.models import ExecuteRequest
from datakeel.api.app import create_app
from datakeel.ask.service import ask_data
from datakeel.catalog.service import import_catalog
from datakeel.cli.enterprise import seed_enterprise_demo
from datakeel.core.ask_models import AskRequest
from datakeel.core.catalog_models import CatalogImportRequest
from datakeel.core.metric_models import Measure, MetricDefinition, MetricTime, SemanticLayer
from datakeel.core.models import JsonDocument
from datakeel.lineage.models import GraphView
from datakeel.storage.metric_store import get_metric, install_layer
from tests.asgi_client import TestClient

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


@pytest.fixture
def catalog_metric(db: Database, tmp_path: Path) -> str:
    """Reflect a real generated SQLite source and register a metric on its columns."""
    source = tmp_path / "catalog-source.sqlite"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE orders (amount INTEGER, date TEXT)")
    import_catalog(
        db,
        CatalogImportRequest(
            source_id="generated", name="Generated source", connection_url=f"sqlite:///{source}"
        ),
    )
    metric = MetricDefinition(
        id="retail_revenue",
        name="Generated retail revenue",
        description="Sum of generated order amounts",
        owner="Generated owner",
        measure=Measure(
            table="generated/main/orders",
            column="generated/main/orders/amount",
            aggregation="sum",
        ),
        time=MetricTime(column="generated/main/orders/date"),
    )
    install_layer(db, SemanticLayer(metrics=[metric]))
    return metric.id


def test_catalog_graph_when_not_requested_keeps_legacy_projection(
    db: Database, catalog_metric: str
) -> None:
    """Catalog objects do not silently change the original graph's meaning."""
    with TestClient(create_app(db)) as client:
        response = client.get(f"/api/lineage/graph?asset_id={catalog_metric}&hops=2")
    assert response.status_code == 200
    assert response.json()["nodes"] == []
    assert response.json()["edges"] == []


def test_catalog_graph_when_requested_exposes_metric_fields_and_table(
    db: Database, catalog_metric: str
) -> None:
    """The public query exposes actual parsed metadata through separately typed edges."""
    with TestClient(create_app(db)) as client:
        response = client.get(
            f"/api/lineage/graph?asset_id={catalog_metric}&hops=2&max_nodes=30&include_catalog=true"
        )
    assert response.status_code == 200
    graph = response.json()
    assert {"metric", "column", "table"} <= {item["asset_type"] for item in graph["nodes"]}
    assert {edge["kind"] for edge in graph["edges"]} == {"catalog"}
    assert all(edge["event_id"] for edge in graph["edges"])
    names = {item["asset_id"]: item["display_name"] for item in graph["nodes"]}
    assert names[catalog_metric] == "Generated retail revenue"
    assert names["generated/main/orders/date"] == "orders.date"


def test_catalog_graph_when_bound_reached_reports_truncation(
    db: Database, catalog_metric: str
) -> None:
    """Catalog projection obeys the existing hard node bound instead of returning a full graph."""
    with TestClient(create_app(db)) as client:
        response = client.get(
            f"/api/lineage/graph?asset_id={catalog_metric}&hops=2&max_nodes=1&include_catalog=true"
        )
    assert response.status_code == 200
    assert len(response.json()["nodes"]) == 1
    assert response.json()["truncated"] is True


def _bounded_catalog(client: TestClient, asset_id: str) -> GraphView:
    response = client.get(
        f"/api/lineage/graph?asset_id={asset_id}&hops=2&max_nodes=30&include_catalog=true"
    )
    assert response.status_code == 200
    result = GraphView.model_validate(response.json())
    assert {"metric", "column", "table"} <= {node.asset_type for node in result.nodes}
    assert len(result.nodes) <= 30
    assert {edge.kind for edge in result.edges} == {"catalog"}
    assert all(
        edge.event_id in {event.event_id for event in result.events} for edge in result.edges
    )
    return result


def _execute(db: Database, action: str, parameters: JsonDocument) -> str:
    plan = actions.prepare_action(db, action, parameters)
    run = actions.execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert run.status == "SUCCEEDED"
    return run.id


def test_catalog_graph_after_controlled_demo_import_and_metric_rollbacks_keeps_real_dependencies(
    db: Database,
) -> None:
    """Receipts and growing answer evidence cannot consume a metadata query's node budget."""
    demo = seed_enterprise_demo(db)
    metric = get_metric(db, "retail_revenue").definition
    changed = metric.model_copy(
        update={"measure": metric.measure.model_copy(update={"aggregation": "count"})}
    )
    request = AskRequest(
        question=demo.answer.question, reference_instant=demo.answer.reference_instant
    )
    with TestClient(create_app(db)) as client:
        initial = _bounded_catalog(client, metric.id)
        assert any(edge.link_type == "derived" for edge in initial.edges)
        _bounded_catalog(client, "shipment_amount")
        run_id = _execute(
            db, "update_metric", JsonDocument({"definition": changed.model_dump(mode="json")})
        )
        assert ask_data(db, request).metric_card is not None
        updated = _bounded_catalog(client, metric.id)
        assert next(node.version for node in updated.nodes if node.asset_id == metric.id) == "2"
        _execute(db, "rollback_metric", JsonDocument({"metric_id": metric.id, "version": 1}))
        assert ask_data(db, request).metric_card is not None
        restored = _bounded_catalog(client, metric.id)
        assert {(edge.source, edge.target, edge.link_type) for edge in restored.edges} == {
            (edge.source, edge.target, edge.link_type) for edge in initial.edges
        }
        receipt = GraphView.model_validate(
            client.get(f"/api/lineage/graph?asset_id={run_id}&hops=1&max_nodes=30").json()
        )
        assert any(edge.operator == "update_metric" for edge in receipt.edges)
        assert any(node.asset_id == metric.id for node in receipt.nodes)
