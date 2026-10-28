# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Object selections and task outputs must not disclose protected captions."""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from datakeel.api.app import create_app
from datakeel.core.models import AssetRef
from datakeel.storage.database import Database, TaskRow
from tests.assets.entry_helpers import grant, publish
from tests.evidence.interface_fixtures import seed_query_evidence

CAPTION = "Generated scene"


def _client(db: Database) -> TestClient:
    return TestClient(create_app(db), headers={"X-Datakeel-Actor": "reader"})


def test_object_selection_and_task_artifacts_when_protected_hide_captions(
    db: Database, tmp_path: Path
) -> None:
    """Frozen selections and task outputs carry captions, so both need the query grant."""
    dataset_id = seed_query_evidence(db, tmp_path / "samples")
    with db.session() as session:
        task_id = session.scalars(select(TaskRow.id).where(TaskRow.dataset_id == dataset_id)).one()
    with _client(db) as client:
        assert (
            CAPTION
            in client.post(
                "/api/ontology/object-sets/evaluate", json={"dataset_id": dataset_id}
            ).text
        )
        assert CAPTION in client.get(f"/api/tasks/{task_id}/artifacts").text
    asset = publish(db, AssetRef(asset_id=dataset_id))
    with _client(db) as client:
        for response in (
            client.post("/api/ontology/object-sets/evaluate", json={"dataset_id": dataset_id}),
            client.post("/api/ontology/object-sets/evaluate", json={}),
            client.get(f"/api/tasks/{task_id}/artifacts"),
        ):
            assert response.status_code == 403
            assert "apply for access" in response.text
            assert CAPTION not in response.text
    grant(db, asset, "valid", "query", subject="reader")
    with _client(db) as client:
        evaluated = client.post(
            "/api/ontology/object-sets/evaluate", json={"dataset_id": dataset_id}
        )
        assert evaluated.status_code == 200
        assert client.get(f"/api/tasks/{task_id}/artifacts").status_code == 200
