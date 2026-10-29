# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Completed exports retain source authorization even when their file manifest is empty."""

from pathlib import Path

from datakeel.actions.models import ActionPlan
from datakeel.api.app import create_app
from datakeel.core.models import AssetRef
from datakeel.harness.training_cases import seed_training_case
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import DatasetInput, create_dataset
from tests.asgi_client import TestClient
from tests.assets.entry_helpers import grant, publish, revoke


def test_empty_manifest_export_download_rechecks_restricted_dataset(db: Database) -> None:
    """Publishing a restriction must guard an already exported metadata-only dataset."""
    dataset = create_dataset(
        db,
        DatasetInput(
            name="Generated metadata-only dataset",
            metadata={"description": "Generated metadata protected after export"},
        ),
    )
    with TestClient(create_app(db)) as client:
        prepared = client.post(
            "/api/actions/export_dataset/prepare",
            json={"dataset_id": dataset.id, "format": "croissant", "destination": "empty.json"},
        )
        assert prepared.status_code == 200, prepared.text
        plan = ActionPlan.model_validate(prepared.json())
        assert plan.manifest.objects == []
        approved = client.post(
            f"/api/approvals/{plan.id}",
            json={"plan_digest": plan.plan_digest, "approve": True},
        )
        assert approved.status_code == 200, approved.text
        executed = client.post(
            f"/api/actions/{plan.id}/execute", json={"plan_digest": plan.plan_digest}
        )
        assert executed.status_code == 200, executed.text
        assert executed.json()["status"] == "SUCCEEDED"
        assert client.get(f"/api/actions/{plan.id}/export").status_code == 200
        publish(db, AssetRef(asset_id=dataset.id))
        assert client.get(f"/api/datasets/{dataset.id}/files").status_code == 403
        response = client.get(f"/api/actions/{plan.id}/export")
        assert response.status_code == 403, response.text


def test_training_reads_share_native_reader_identity_and_current_grants(
    db: Database, tmp_path: Path
) -> None:
    """A browser query uses the same local reader as files, and loses access on revocation."""
    fixture = seed_training_case(db, tmp_path)
    asset = publish(db, AssetRef(asset_id=fixture.dataset_id, version=fixture.version_id))
    base = f"/api/datasets/{fixture.dataset_id}/versions/{fixture.version_id}/training"
    with TestClient(create_app(db)) as client:
        assert client.get(f"{base}/splits").status_code == 403
        identity = grant(db, asset, "valid", "query", subject="local-user")
        assert identity is not None
        assert client.get(f"/api/datasets/{fixture.dataset_id}/files").status_code == 200
        assert client.get(f"{base}/splits").status_code == 200
        assert (
            client.get(f"{base}/splits", headers={"X-Datakeel-Actor": "local"}).status_code == 403
        )
        assert client.post(f"{base}/preview", json={"name": "permitted"}).status_code == 200
        revoke(db, identity)
        assert client.get(f"{base}/splits").status_code == 403
