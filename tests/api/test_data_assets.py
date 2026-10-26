# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Market and authorization HTTP contracts call the actual local domain pipeline."""

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from datakeel.actions.models import ActionPlan
from datakeel.api.app import create_app
from datakeel.core.data_asset_models import (
    AssetApplication,
    AssetGrant,
    AssetMarketPage,
    DataAssetCard,
)
from datakeel.core.models import JsonDocument, utcnow
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths


def _action(client: TestClient, name: str, body: JsonDocument) -> None:
    response = client.post(f"/api/actions/{name}/prepare", json=body.root)
    assert response.status_code == 200, response.text
    plan = ActionPlan.model_validate(response.json())
    if plan.requires_approval:
        approval = client.post(
            f"/api/approvals/{plan.id}",
            json={"plan_digest": plan.plan_digest, "approve": True},
        )
        assert approval.status_code == 200
    response = client.post(
        f"/api/actions/{plan.id}/execute", json={"plan_digest": plan.plan_digest}
    )
    assert response.status_code == 200, response.text


@pytest.fixture
def asset_client(db: Database, tmp_path: Path) -> TestClient:
    """Expose a draft asset referencing one independently generated dataset."""
    path = tmp_path / "fixture.txt"
    path.write_text("Independent generated data", encoding="utf-8")
    dataset = import_paths(db, "Generated HTTP dataset", [path])
    client = TestClient(create_app(db))
    _action(
        client,
        "create_data_asset",
        JsonDocument(
            {
                "definition": {
                    "name": "Daily sales",
                    "owner": "steward",
                    "classification": "request",
                    "tags": ["sales"],
                    "target": {"asset_id": dataset.id},
                }
            }
        ),
    )
    return client


def _asset(client: TestClient) -> str:
    page = AssetMarketPage.model_validate(
        client.get("/api/data-assets?include_unpublished=true&search=sales").json()
    )
    return page.items[0].asset.id


def test_market_management_when_search_includes_drafts_returns_typed_card(
    asset_client: TestClient,
) -> None:
    """Draft management combines filters and flags without dropping typed query fields."""
    assert AssetMarketPage.model_validate(asset_client.get("/api/data-assets").json()).total == 0
    identity = _asset(asset_client)
    card = DataAssetCard.model_validate(asset_client.get(f"/api/data-assets/{identity}").json())
    assert card.asset.definition.name == "Daily sales"
    assert card.asset.status == "draft"
    history = asset_client.get(f"/api/data-assets/{identity}/history")
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert asset_client.get("/api/data-assets?sort=unsupported").status_code == 422


def test_http_application_decision_and_revocation_have_visible_progress(
    asset_client: TestClient,
) -> None:
    """A submitted request, signed grant and revocation appear on independent typed reads."""
    identity = _asset(asset_client)
    _action(asset_client, "publish_data_asset", JsonDocument({"asset_id": identity}))
    response = asset_client.post(
        f"/api/data-assets/{identity}/applications",
        json={
            "applicant": "reader",
            "purpose": "Sales planning",
            "scopes": ["query"],
            "expires_at": (utcnow() + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    application = AssetApplication.model_validate(response.json())
    assert application.status == "pending"
    _action(
        asset_client,
        "decide_asset_application",
        JsonDocument({"application_id": application.id, "approve": True}),
    )
    decided = AssetApplication.model_validate(
        asset_client.get(f"/api/data-assets/applications/{application.id}").json()
    )
    assert decided.grant_id is not None
    grant = AssetGrant.model_validate(
        asset_client.get(f"/api/data-assets/grants/{decided.grant_id}").json()
    )
    assert grant.subject == "reader"
    _action(asset_client, "revoke_asset_grant", JsonDocument({"grant_id": grant.id}))
    assert asset_client.get(f"/api/data-assets/grants/{grant.id}").json()["revoked_by"] == "local"
    assert len(asset_client.get(f"/api/data-assets/{identity}/applications").json()) == 1
    assert len(asset_client.get("/api/data-assets/applications?applicant=reader").json()) == 1
    assert len(asset_client.get("/api/data-assets/grants?subject=reader").json()) == 1
    assert len(asset_client.get(f"/api/data-assets/{identity}/control-history").json()) == 3
    assert asset_client.get(f"/api/data-assets/audit?asset_id={identity}&actor=reader").json() == []
