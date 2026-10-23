# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real paginated metadata navigation and metric history through HTTP."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from datakeel.api.app import create_app
from datakeel.core.catalog_models import (
    CatalogObject,
    CatalogPage,
    CatalogTableDetail,
    ImpactResult,
)
from datakeel.core.metric_history_models import MetricHistory
from datakeel.core.metric_models import MetricCard
from tests.enterprise_support import enterprise_fixture

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


@pytest.fixture
def catalog_client(db: Database, tmp_path: Path) -> TestClient:
    """Expose a fully reflected synthetic enterprise in an isolated application."""
    enterprise_fixture(db, tmp_path / "enterprise")
    return TestClient(create_app(db))


def test_collections_when_filtered_paginate_before_returning(catalog_client: TestClient) -> None:
    """Source, table, and column pages retain full counts and apply source/parent filters."""
    assert CatalogPage.model_validate(catalog_client.get("/api/catalog/sources").json()).total == 4
    tables = CatalogPage.model_validate(
        catalog_client.get("/api/catalog/tables?source_id=erp&offset=1&limit=2").json()
    )
    assert tables.total == 6
    assert len(tables.items) == 2
    assert all(item.source_id == "erp" for item in tables.items)
    columns = CatalogPage.model_validate(
        catalog_client.get(
            "/api/catalog/columns",
            params={"parent_id": "ecommerce/main/orders", "search": "paid_amount"},
        ).json()
    )
    assert columns.total == 1
    assert columns.items[0].name == "paid_amount"


def test_table_when_addressed_exposes_fields_consumers_and_owners(
    catalog_client: TestClient,
) -> None:
    """The table details derive related metrics and ownership from actual catalog edges."""
    identity = "ecommerce/main/orders"
    response = catalog_client.get(f"/api/catalog/tables/{quote(identity, safe='')}")
    assert response.status_code == 200
    detail = CatalogTableDetail.model_validate(response.json())
    assert detail.columns
    assert detail.metrics
    assert detail.owners
    assert detail.table.asset_ref.asset_id == identity
    assert detail.neighbors.links
    item = CatalogObject.model_validate(
        catalog_client.get(f"/api/catalog/objects/{quote(identity, safe='')}").json()
    )
    assert item == detail.table


def test_metric_when_read_returns_current_definition_and_history(
    catalog_client: TestClient,
) -> None:
    """Expose typed current and historical metric cards with attributable changes."""
    assert CatalogPage.model_validate(catalog_client.get("/api/catalog/metrics").json()).total >= 12
    metric = MetricCard.model_validate(
        catalog_client.get("/api/catalog/metrics/retail_revenue").json()
    )
    assert metric.definition.owner
    history = MetricHistory.model_validate(
        catalog_client.get("/api/catalog/metrics/retail_revenue/history").json()
    )
    assert history.versions == (metric,)
    assert history.audit == ()
    assert (
        CatalogPage.model_validate(catalog_client.get("/api/catalog/dimensions").json()).total >= 6
    )
    assert CatalogPage.model_validate(catalog_client.get("/api/catalog/terms").json()).total >= 30


def test_neighbors_and_impact_when_column_requested_return_explicit_relationships(
    catalog_client: TestClient,
) -> None:
    """Navigate nearby fields and downstream semantics without an unbounded graph."""
    identity = "ecommerce/main/orders/paid_amount"
    adjacent = ImpactResult.model_validate(
        catalog_client.get("/api/catalog/neighbors", params={"asset_id": identity}).json()
    )
    downstream = ImpactResult.model_validate(
        catalog_client.get(
            "/api/catalog/impact", params={"asset_id": identity, "max_nodes": 100}
        ).json()
    )
    assert adjacent.links
    assert {"column", "table", "metric", "term"} <= {
        item.asset_ref.asset_type for item in downstream.objects
    }


@pytest.mark.parametrize(
    "path",
    [
        "/api/catalog/objects/absent",
        "/api/catalog/tables/absent",
        "/api/catalog/metrics/absent",
        "/api/catalog/metrics/absent/history",
        "/api/catalog/neighbors?asset_id=absent",
    ],
)
def test_catalog_when_identity_unknown_returns_not_found(
    catalog_client: TestClient, path: str
) -> None:
    """Missing identities never become empty success responses."""
    assert catalog_client.get(path).status_code == 404


def test_catalog_when_pagination_invalid_rejects_before_reading(catalog_client: TestClient) -> None:
    """Limit and collection validation bound public catalog navigation."""
    assert catalog_client.get("/api/catalog/tables?limit=1001").status_code == 422
    assert catalog_client.get("/api/catalog/tables?offset=-1").status_code == 422
    assert catalog_client.get("/api/catalog/unknown").status_code == 422
