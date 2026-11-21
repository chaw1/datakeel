# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""HTTP memory search and edits retain validation, identity and dataset boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, prepare_action
from datakeel.api.app import create_app
from datakeel.core.memory_models import MemoryCreate, MemoryEntry, MemoryPolicy
from datakeel.core.models import JsonDocument, new_id, utcnow
from datakeel.dataset_store.dataset_service import DatasetInput, create_dataset
from datakeel.memory.service import create_memory, get_memory, reinforce_memories
from tests.asgi_client import TestClient

if TYPE_CHECKING:
    from collections.abc import Mapping

    from datakeel.storage.database import Database


def _manage(db: Database, values: Mapping[str, object]) -> None:
    plan = prepare_action(
        db, "manage_users", JsonDocument.model_validate({"request_id": new_id(), **values})
    )
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))


def test_memory_search_ranks_strength_and_matches_identifiers_substrings_and_scope(
    db: Database,
) -> None:
    """Single tokens and literal substrings remain searchable within the requested scope."""
    dataset = create_dataset(db, DatasetInput(name="search scope"))
    other = create_dataset(db, DatasetInput(name="other scope"))
    now = utcnow()
    memories = [
        create_memory(
            db,
            MemoryCreate(content="Qwen3.5 IoU_50 ds_001 华东 revenue v2", dataset_id=scope),
            clock=lambda: now,
        )
        for scope in (None, dataset.id, other.id)
    ]
    reinforce_memories(db, [memories[1].id], clock=lambda: now)
    with TestClient(create_app(db)) as client:
        for query in ("v2", "QWEN3.5", "wen", "华东", "IOU_50", "ds_001"):
            response = client.get(
                "/api/agent/memories", params={"q": query, "dataset_id": dataset.id}
            )
            assert response.status_code == 200
            results = [MemoryEntry.model_validate(item) for item in response.json()]
            assert [item.id for item in results] == [memories[1].id, memories[0].id]
        assert client.get("/api/agent/memories", params={"q": "absent"}).json() == []
        unfiltered = client.get("/api/agent/memories").json()
        blank = client.get("/api/agent/memories", params={"q": "  "}).json()
        assert [item["id"] for item in blank] == [item["id"] for item in unfiltered]


def test_memory_patch_redacts_and_persists_only_content(db: Database) -> None:
    """The edited response and the following GET both use server-redacted content."""
    memory = create_memory(db, MemoryCreate(content="original memory"))
    with TestClient(create_app(db)) as client:
        response = client.patch(
            f"/api/agent/memories/{memory.id}", json={"content": "  v2 user@example.org  "}
        )
        assert response.status_code == 200, response.text
        edited = MemoryEntry.model_validate(response.json())
        assert edited.content == "v2 [REDACTED]"
        assert edited.model_dump(exclude={"content", "current_strength"}) == memory.model_dump(
            exclude={"content", "current_strength"}
        )
        assert client.get(f"/api/agent/memories/{memory.id}").json()["content"] == edited.content


def test_memory_patch_rejects_invalid_content_missing_and_archived_entries(db: Database) -> None:
    """Blank or oversized content and scope changes are rejected before persistence."""
    memory = create_memory(db, MemoryCreate(content="original memory"))
    reinforce_memories(db, [memory.id])
    merged = create_memory(
        db, MemoryCreate(content="original memory"), policy=MemoryPolicy(max_entries=1)
    )
    with TestClient(create_app(db)) as client:
        for body in (
            {"content": ""},
            {"content": " \n\t "},
            {"content": "x" * 6001},
            {"content": "new", "dataset_id": "other"},
        ):
            response = client.patch(f"/api/agent/memories/{merged.id}", json=body)
            assert response.status_code == 422, response.text
        for identifier in ("missing", merged.source_memory_ids[0]):
            response = client.patch(
                f"/api/agent/memories/{identifier}", json={"content": "replacement"}
            )
            assert response.status_code == 404, response.text
        assert get_memory(db, merged.id).content == "original memory"


def test_memory_patch_uses_named_actor_and_rejects_missing_write_scope(db: Database) -> None:
    """A named administrator can edit after local is disabled; an observer cannot."""
    memory = create_memory(db, MemoryCreate(content="original memory"))
    _manage(db, {"operation": "create", "user_id": "local"})
    _manage(db, {"operation": "create", "user_id": "writer", "role_ids": ["administrator"]})
    _manage(db, {"operation": "create", "user_id": "observer", "role_ids": ["acceptance"]})
    _manage(db, {"operation": "update", "user_id": "local", "status": "disabled"})
    with TestClient(create_app(db)) as client:
        for actor in ("unknown", "observer"):
            response = client.patch(
                f"/api/agent/memories/{memory.id}",
                json={"content": "forbidden"},
                headers={"X-Datakeel-Actor": actor},
            )
            assert response.status_code == 403, response.text
        response = client.patch(
            f"/api/agent/memories/{memory.id}",
            json={"content": "authorized edit"},
            headers={"X-Datakeel-Actor": "writer"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["content"] == "authorized edit"
