# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest
    from pydantic import JsonValue

    from datakeel.storage.database import Database

import base64

from datakeel.api.app import create_app
from datakeel.worker.runner import run_worker
from tests.asgi_client import TestClient


def dataset(client: TestClient) -> dict[str, JsonValue]:
    """Provide the dataset test fixture."""
    response = client.post(
        "/api/datasets",
        json={
            "name": "generated-texts",
            "files": [
                {
                    "filename": "sample.txt",
                    "content_base64": base64.b64encode(
                        b"A detailed generated observation."
                    ).decode(),
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_dataset_task_download_quality_report_and_export(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify dataset task download quality report and export."""
    with TestClient(create_app(db)) as client:
        identifier = dataset(client)
        assert len(client.get("/api/datasets").json()) == 1
        files = client.get(f"/api/datasets/{identifier}/files").json()
        assert len(files) == 1
        assert "path" not in files[0]
        assert (
            client.get(f"/api/datasets/{identifier}/files/{files[0]['id']}/download").content
            == b"A detailed generated observation."
        )
        response = client.post(
            "/api/tasks", json={"dataset_id": identifier, "idempotency_key": "one"}
        )
        assert response.status_code == 202, response.text
        task_id = response.json()["id"]
        assert (
            client.post(
                "/api/tasks", json={"dataset_id": identifier, "idempotency_key": "one"}
            ).json()["id"]
            == task_id
        )
        run_worker(db, once=True)
        task = client.get(f"/api/tasks/{task_id}").json()
        assert task["state"] == "COMPLETED", task
        assert len(client.get(f"/api/datasets/{identifier}/versions").json()) == 2
        assert client.get(f"/api/tasks/{task_id}/artifacts").json()
        graph = client.get("/api/lineage/graph", params={"asset": identifier}).json()
        assert len(graph["edges"]) >= 11
        events = graph["events"]
        assert client.post("/api/lineage/events", json=events[0]).json() == {"inserted": False}
        initial = client.get(f"/api/datasets/{identifier}/quality").json()
        changed = client.put(
            f"/api/datasets/{identifier}/quality/config", json={"min_size_bytes": 999999}
        ).json()
        assert changed["total"] != initial["total"]
        report = client.get(f"/api/datasets/{identifier}/report").json()
        assert len(report["chapters"]) == 6
        monkeypatch.setenv("DATAKEEL_LLM_URL", "http://127.0.0.1:1/unavailable")
        fallback = client.get(f"/api/datasets/{identifier}/report").json()
        assert fallback["fallback"] is True
        assert len(fallback["chapters"]) == 6
        assert client.get(
            "/api/export", params={"format": "openlineage", "dataset_id": identifier}
        ).json()
        croissant = client.get(
            "/api/export", params={"format": "croissant", "dataset_id": identifier}
        ).json()
        assert {"@context", "distribution", "recordSet"} <= croissant.keys()


def test_governance_rejects_invalid_records_and_logs_fields(db: Database) -> None:
    """Verify governance rejects invalid records and logs fields."""
    with TestClient(create_app(db)) as client:
        identifier = dataset(client)
        root = f"/api/datasets/{identifier}"
        template = {
            "type": "object",
            "required": ["license", "code"],
            "properties": {
                "license": {"type": "string", "enum": ["Apache-2.0"]},
                "code": {"type": "string", "pattern": "^[A-Z]{3}$"},
            },
        }
        assert client.put(root + "/template", json=template).status_code == 200
        before = client.get(root + "/compliance").json()
        for values in (
            {},
            {"license": "unknown", "code": "ABC"},
            {"license": "Apache-2.0", "code": "bad"},
        ):
            assert (
                client.put(
                    root + "/metadata", json={"values": values, "reason": "test"}
                ).status_code
                == 422
            )
        assert client.get(root + "/metadata/changes").json() == []
        saved = client.put(
            root + "/metadata",
            json={
                "values": {"license": "Apache-2.0", "code": "ABC"},
                "source": "test",
                "reason": "apply standard",
            },
        )
        assert saved.status_code == 200, saved.text
        changes = client.get(root + "/metadata/changes").json()
        assert {value["field"] for value in changes} == {"license", "code"}
        assert all(value["reason"] == "apply standard" for value in changes)
        after = client.get(root + "/compliance").json()
        assert after != before


def test_invalid_routes_and_upload_names(db: Database) -> None:
    """Verify invalid routes and upload names."""
    with TestClient(create_app(db)) as client:
        assert client.get("/api/datasets/missing").status_code == 404
        response = client.post(
            "/api/datasets",
            json={"name": "invalid", "files": [{"filename": "../escape", "content_base64": ""}]},
        )
        assert response.status_code == 422
