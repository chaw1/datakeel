# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Current grants cover returned transcripts, immutable streams and attributed memories."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation
from datakeel.api.app import create_app
from datakeel.core.agent_models import ConversationCreate, ModelResponse, ToolCall
from datakeel.core.data_asset_models import AssetUsageQuery
from datakeel.core.memory_models import MemoryCreate
from datakeel.core.models import AssetRef, JsonDocument, utcnow
from datakeel.memory.service import create_memory, delete_memory
from datakeel.storage.conversation_store import get
from datakeel.storage.data_asset_access import list_usage
from datakeel.storage.dataset_service import import_paths
from datakeel.storage.memory_rows import MemoryRow
from tests.assets.entry_helpers import grant, publish, revoke

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi import FastAPI

    from datakeel.storage.database import Database

MARKER = "generated-protected-84621.txt"


def history_fixture(
    db: Database, tmp_path: Path
) -> tuple[TestClient, str, FakeProvider, str, list[str]]:
    """Run a real protected read and return its source-attributed memory controls."""
    document = tmp_path / MARKER
    document.write_text("Generated protected record: 84621.", encoding="utf-8")
    dataset = import_paths(db, "Generated history boundary", [document])
    asset = publish(db, AssetRef(asset_id=dataset.id))
    grant_id = grant(db, asset, "valid", "query")
    assert grant_id
    conversation = create_conversation(db, ConversationCreate())
    provider = FakeProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCall(
                        id="fixture-read",
                        name="search_files",
                        arguments=JsonDocument({"dataset_id": dataset.id}),
                    )
                ]
            ),
            ModelResponse(content=f"The protected generated filename is {MARKER}"),
        ]
    )
    app = create_app(db)
    app.state.agent_provider = provider
    client = TestClient(app)
    endpoint = f"/api/agent/conversations/{conversation.id}/messages"
    first = client.post(endpoint, json=history_request())
    assert first.status_code == 200
    assert MARKER in first.text
    memories = [
        create_memory(
            db,
            MemoryCreate(
                content=f"Source-attributed generated filename {MARKER}",
                source_conversation_id=conversation.id,
            ),
        ),
        create_memory(db, MemoryCreate(content=f"Dataset note {MARKER}", dataset_id=dataset.id)),
        create_memory(db, MemoryCreate(content="Prefer concise replies with examples.")),
    ]
    return client, conversation.id, provider, grant_id, [item.id for item in memories]


def history_request() -> dict[str, str]:
    """Keep the original immutable response key available to replay regressions."""
    return {"content": "Find the generated document", "idempotency_key": "history-probe"}


def usage_count(db: Database) -> int:
    """Count append-only usage facts independently of the response under test."""
    return len(list_usage(db, AssetUsageQuery()))


def test_authorized_history_replays_and_memory_reads_are_audited_once(
    db: Database, tmp_path: Path
) -> None:
    """Each complete response audits its deduplicated asset set without another model call."""
    client, identifier, provider, _, memories = history_fixture(db, tmp_path)
    endpoints = [
        f"/api/agent/conversations/{identifier}",
        "/api/agent/conversations",
        f"/api/agent/memories/{memories[0]}",
        "/api/agent/memories",
    ]
    for endpoint in endpoints:
        before = usage_count(db)
        response = client.get(endpoint)
        assert response.status_code == 200
        assert MARKER in response.text
        assert usage_count(db) == before + 1
    before = usage_count(db)
    replay = client.post(f"/api/agent/conversations/{identifier}/messages", json=history_request())
    assert replay.status_code == 200
    assert MARKER in replay.text
    assert usage_count(db) == before + 1
    assert len(provider.requests) == 2
    assert all(
        item.entry == "agent" and item.scope == "query"
        for item in list_usage(db, AssetUsageQuery())
    )


def invalidate(db: Database, identifier: str, state: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Revoke a grant or advance only the guard's injected clock past its expiry."""
    if state == "revoked":
        revoke(db, identifier)
    else:
        future = utcnow() + timedelta(hours=2)
        monkeypatch.setattr("datakeel.storage.data_asset_access.utcnow", lambda: future)


@pytest.mark.parametrize("state", ["revoked", "expired"])
def test_lost_grants_filter_http_history_and_memories_and_reject_cached_streams(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    """Stored facts survive, but neither replay nor a later model request discloses them."""
    client, identifier, provider, grant_id, memories = history_fixture(db, tmp_path)
    stored = get(db, identifier)
    invalidate(db, grant_id, state, monkeypatch)
    before = usage_count(db)
    for endpoint in (f"/api/agent/conversations/{identifier}", "/api/agent/conversations"):
        response = client.get(endpoint)
        assert response.status_code == 200
        assert MARKER not in response.text
        assert "Find the generated document" in response.text
    replay = client.post(f"/api/agent/conversations/{identifier}/messages", json=history_request())
    assert replay.status_code == 403
    assert MARKER not in replay.text
    assert "apply for access" in replay.text
    assert len(provider.requests) == 2
    for memory_id in memories[:2]:
        response = client.get(f"/api/agent/memories/{memory_id}")
        assert response.status_code == 403
        assert MARKER not in response.text
    visible = client.get("/api/agent/memories")
    assert visible.status_code == 200
    assert [item["id"] for item in visible.json()] == [memories[2]]
    assert client.get(f"/api/agent/memories/{memories[2]}").status_code == 200
    assert usage_count(db) == before
    _assert_facts_preserved(db, identifier, stored.model_dump_json(), memories[:2])
    assert_fresh_context(client, identifier)
    assert usage_count(db) == before


def _assert_facts_preserved(
    db: Database, identifier: str, stored: str, memories: list[str]
) -> None:
    assert get(db, identifier).model_dump_json() == stored
    with db.session() as session:
        rows = list(session.scalars(select(MemoryRow).where(MemoryRow.id.in_(memories))))
        assert len(rows) == 2
        assert all(MARKER in str(row.payload) for row in rows)


def assert_fresh_context(client: TestClient, identifier: str) -> None:
    """Check the actual next provider request cannot see the previously derived marker."""
    fresh = FakeProvider([ModelResponse(content="Safe fallback without former data.")])
    cast("FastAPI", client.app).state.agent_provider = fresh
    response = client.post(
        f"/api/agent/conversations/{identifier}/messages",
        json={"content": "What is the next step?", "idempotency_key": "fresh-turn"},
    )
    assert response.status_code == 200
    assert MARKER not in response.text
    assert len(fresh.requests) == 1
    assert MARKER not in fresh.requests[0].model_dump_json()


@pytest.mark.parametrize("deleted", [False, True])
@pytest.mark.parametrize("state", ["revoked", "expired"])
def test_memory_derived_response_keeps_resource_snapshot_after_hard_delete(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    *,
    deleted: bool,
) -> None:
    """A consumer with no tool calls remains protected after its source memory disappears."""
    client, source_id, _, grant_id, _ = history_fixture(db, tmp_path)
    memory = create_memory(
        db,
        MemoryCreate(
            content=f"Quarterly shipment review tracks {MARKER}",
            source_conversation_id=source_id,
        ),
    )
    conversation = create_conversation(db, ConversationCreate())
    provider = FakeProvider([ModelResponse(content=f"Derived filename: {MARKER}")])
    cast("FastAPI", client.app).state.agent_provider = provider
    request = {"content": "Quarterly shipment review", "idempotency_key": "memory-consumer"}
    endpoint = f"/api/agent/conversations/{conversation.id}"
    initial = client.post(f"{endpoint}/messages", json=request)
    assert initial.status_code == 200
    assert MARKER in provider.requests[0].model_dump_json()
    stored = get(db, conversation.id)
    assert stored.memory_sources
    assert MARKER not in str(stored.memory_sources)
    if deleted:
        delete_memory(db, memory.id)
    invalidate(db, grant_id, state, monkeypatch)
    before = usage_count(db)
    response = client.get(endpoint)
    assert response.status_code == 200
    assert MARKER not in response.text
    replay = client.post(f"{endpoint}/messages", json=request)
    assert replay.status_code == 403
    assert MARKER not in replay.text
    assert len(provider.requests) == 1
    assert usage_count(db) == before
    assert get(db, conversation.id) == stored


def test_deleted_unattributed_global_preference_keeps_ordinary_history_replay(db: Database) -> None:
    """A recorded empty resource set preserves the existing semantics of personal preferences."""
    preference = "Use short sentences and practical examples."
    memory = create_memory(db, MemoryCreate(content=preference))
    conversation = create_conversation(db, ConversationCreate())
    provider = FakeProvider([ModelResponse(content="Preference acknowledged.")])
    app = create_app(db)
    app.state.agent_provider = provider
    client = TestClient(app)
    request = {
        "content": "short sentences practical examples",
        "idempotency_key": "plain-preference",
    }
    endpoint = f"/api/agent/conversations/{conversation.id}"
    initial = client.post(f"{endpoint}/messages", json=request)
    assert initial.status_code == 200
    assert preference in provider.requests[0].model_dump_json()
    assert get(db, conversation.id).memory_sources[0].asset_refs == ()
    delete_memory(db, memory.id)
    history = client.get(endpoint)
    assert history.status_code == 200
    assert "Preference acknowledged." in history.text
    assert "memory_sources" not in history.json()
    assert client.post(f"{endpoint}/messages", json=request).text == initial.text
    assert len(provider.requests) == 1
    assert list_usage(db, AssetUsageQuery()) == ()
