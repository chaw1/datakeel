# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated child tasks retain their parent's protected source boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from sqlalchemy import select

from datakeel.agent.providers import FakeProvider
from datakeel.core.agent_models import ModelResponse, ScriptedResponse, ToolCall
from datakeel.core.models import JsonDocument
from datakeel.memory.service import delete_memory
from datakeel.storage.conversation_rows import ConversationRequestRow
from datakeel.storage.conversation_store import get, list_all
from datakeel.storage.tool_invocations import list_invocations
from tests.assets.entry_helpers import revoke
from tests.assets.test_agent_history_reads import MARKER, history_fixture

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from datakeel.core.agent_models import Conversation
    from datakeel.storage.database import Database


def _delegation_provider() -> FakeProvider:
    return FakeProvider(
        [
            ScriptedResponse(
                agent="main",
                tool_calls=[
                    ToolCall(
                        name="tool_search", arguments=JsonDocument({"query": "delegate_agent"})
                    )
                ],
            ),
            ScriptedResponse(
                agent="main",
                tool_calls=[
                    ToolCall(
                        name="delegate_agent",
                        arguments=JsonDocument(
                            {"agent": "catalog-analyst", "task": f"Review {MARKER}"}
                        ),
                    )
                ],
            ),
            ScriptedResponse(agent="catalog-analyst", content=f"Reviewed {MARKER}"),
            ScriptedResponse(agent="main", content="Specialist review complete."),
        ]
    )


def _assert_child_replay_denied(
    db: Database, client: TestClient, child: Conversation, provider: FakeProvider
) -> None:
    with db.session() as session:
        request = session.scalar(
            select(ConversationRequestRow).where(ConversationRequestRow.conversation_id == child.id)
        )
        assert request is not None
        body = {"content": request.content, "idempotency_key": request.key}
    before = len(provider.requests)
    response = client.post(f"/api/agent/conversations/{child.id}/messages", json=body)
    assert response.status_code == 403
    assert MARKER not in response.text
    assert "apply for access" in response.text
    assert len(provider.requests) == before


def _assert_fresh_child_context(client: TestClient, child: Conversation) -> None:
    fresh = FakeProvider([ModelResponse(content="Safe continuation without former data.")])
    cast("FastAPI", client.app).state.agent_provider = fresh
    response = client.post(
        f"/api/agent/conversations/{child.id}/messages",
        json={"content": "Continue safely", "idempotency_key": "fresh-child-turn"},
    )
    assert response.status_code == 200
    assert MARKER not in response.text
    assert len(fresh.requests) == 1
    assert MARKER not in fresh.requests[0].model_dump_json()


def test_generated_child_task_is_hidden_after_parent_source_grant_revocation(
    db: Database, tmp_path: Path
) -> None:
    """A child with no tools or memories cannot expose inherited task text after revocation."""
    client, parent_id, _, grant_id, memories = history_fixture(db, tmp_path)
    for memory_id in memories:
        delete_memory(db, memory_id)
    provider = _delegation_provider()
    cast("FastAPI", client.app).state.agent_provider = provider
    response = client.post(
        f"/api/agent/conversations/{parent_id}/messages",
        json={
            "content": "Ask a specialist to review the prior result",
            "idempotency_key": "review",
        },
    )
    assert response.status_code == 200
    assert MARKER in response.text
    assert len(provider.requests) == 4
    assert provider.script_errors == []
    child = next(
        item
        for item in list_all(db, include_children=True)
        if item.parent_conversation_id == parent_id
    )
    assert any(message.role == "user" and MARKER in message.content for message in child.messages)
    assert MARKER in provider.requests[2].model_dump_json()
    assert list_invocations(db, child.id) == []
    assert child.memory_sources == ()
    parent = get(db, parent_id)
    revoke(db, grant_id)
    history = client.get(f"/api/agent/conversations/{child.id}")
    assert history.status_code == 200
    assert MARKER not in history.text
    _assert_child_replay_denied(db, client, child, provider)
    assert get(db, parent_id) == parent
    assert get(db, child.id) == child
    _assert_fresh_child_context(client, child)
    assert get(db, child.id).messages[: len(child.messages)] == child.messages
