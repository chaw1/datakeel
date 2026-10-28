# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""HTTP memory management validates scopes and never returns deleted content in audit."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.api.app import create_app
from datakeel.core.memory_models import MemoryDeletion, MemoryEntry
from tests.asgi_client import TestClient

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_memory_api_when_created_listed_and_deleted_keeps_only_content_free_audit(
    db: Database,
) -> None:
    """The manual management path shares PII filtering, strength fields and hard deletion."""
    with TestClient(create_app(db)) as client:
        created = client.post(
            "/api/agent/memories",
            json={"content": "revenue metric owner user@example.org", "idempotency_key": "manual"},
        )
        assert created.status_code == 200
        entry = MemoryEntry.model_validate(created.json())
        assert entry.content == "revenue metric owner [REDACTED]"
        assert entry.current_strength == 1
        assert client.get("/api/agent/memories").json()[0]["id"] == entry.id
        assert client.get(f"/api/agent/memories/{entry.id}").status_code == 200
        deleted = client.delete(f"/api/agent/memories/{entry.id}")
        audit = MemoryDeletion.model_validate(deleted.json())
        assert audit.deleted_ids == [entry.id]
        assert client.get("/api/agent/memories").json() == []
        assert client.get(f"/api/agent/memories/{entry.id}").status_code == 404
        assert client.get("/api/agent/memories/audit").json() == [audit.model_dump(mode="json")]
        assert "revenue" not in client.get("/api/agent/memories/audit").text


def test_memory_api_when_invalid_or_unknown_scope_returns_typed_errors(db: Database) -> None:
    """Blank entries, unknown fields and nonexistent datasets cannot bypass API validation."""
    with TestClient(create_app(db)) as client:
        for body in ({"content": " "}, {"content": "value", "unknown": True}):
            assert client.post("/api/agent/memories", json=body).status_code == 422
        assert (
            client.post(
                "/api/agent/memories", json={"content": "value", "dataset_id": "missing"}
            ).status_code
            == 404
        )
        assert client.delete("/api/agent/memories/missing").status_code == 404


def test_memory_api_when_filtered_includes_only_global_and_requested_dataset(db: Database) -> None:
    """The HTTP dataset filter exposes the same scope union as conversation retrieval."""
    with TestClient(create_app(db)) as client:
        dataset = client.post("/api/datasets", json={"name": "memory-scope"}).json()
        for scope in (None, dataset["id"]):
            response = client.post(
                "/api/agent/memories", json={"content": "revenue metric", "dataset_id": scope}
            )
            assert response.status_code == 200
        assert (
            len(client.get("/api/agent/memories", params={"dataset_id": dataset["id"]}).json()) == 2
        )
        assert len(client.get("/api/agent/memories", params={"dataset_id": "other"}).json()) == 1
