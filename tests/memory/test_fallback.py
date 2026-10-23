# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Fallback attempts must not resend memory deleted during an earlier provider attempt."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from datakeel.agent.service import create_conversation, send_message
from datakeel.core.agent_models import MessageInput
from datakeel.core.memory_models import MemoryCreate
from datakeel.harness.service import list_traces
from datakeel.memory.service import create_memory, delete_memory, get_memory, list_memories
from datakeel.runtime.chat_provider import model_provider
from tests.memory.helpers import freeze_memory_clock
from tests.routing.protocol_helpers import FailingTransport, configure_fallback

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from datakeel.storage.database import Database


class DeletingTransport(FailingTransport):
    """Commit a real memory deletion while the first mock provider call is in flight."""

    def __init__(self, db: Database, memory_id: str) -> None:
        """Use the existing offline transient-failure fixture and capture actual wire bodies."""
        super().__init__("openai", 500)
        self.db, self.memory_id = db, memory_id
        self.bodies: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Delete before the failure is returned, then allow the normal fallback response."""
        self.bodies.append(request.content.decode())
        if len(self.bodies) == 1:
            delete_memory(self.db, self.memory_id)
        return super().__call__(request)


def test_fallback_when_memory_deleted_during_first_attempt_refreshes_prompt_and_trace(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The backup call accounts its fresh context and does not restore the deleted entry."""
    config, settings, _backup = configure_fallback(tmp_path, monkeypatch, "openai")
    entry = create_memory(db, MemoryCreate(content="revenue metric excludes generated refund rows"))
    conversation = create_conversation(db, config)
    transport = DeletingTransport(db, entry.id)
    with (
        httpx.Client(transport=httpx.MockTransport(transport), trust_env=False) as client,
        model_provider(config, settings, client) as provider,
    ):
        events = list(
            send_message(
                db,
                conversation.id,
                MessageInput(content="Explain revenue metric"),
                provider=provider,
            )
        )
    assert len(transport.bodies) == 2
    assert entry.content in transport.bodies[0]
    assert entry.content not in transport.bodies[1]
    assert list_memories(db, include_archived=True) == []
    assert events[-1].used_memory_ids == [entry.id]
    traces = list_traces(db, conversation.id)
    assert any(segment.name == "memory" for segment in traces[0].segments)
    assert not any(segment.name == "memory" for segment in traces[1].segments)


def test_fallback_when_memory_remains_live_strengthens_once_per_question(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The failed primary and successful backup share one user-question reinforcement."""
    clock = freeze_memory_clock(monkeypatch)
    config, settings, _backup = configure_fallback(tmp_path, monkeypatch, "openai")
    entry = create_memory(
        db, MemoryCreate(content="revenue metric excludes generated refund rows"), clock=clock
    )
    conversation = create_conversation(db, config)
    transport = FailingTransport("openai", 500)
    with (
        httpx.Client(transport=httpx.MockTransport(transport), trust_env=False) as client,
        model_provider(config, settings, client) as provider,
    ):
        events = list(
            send_message(
                db,
                conversation.id,
                MessageInput(content="Explain revenue metric"),
                provider=provider,
            )
        )
    assert len(transport.models) == 2
    used = get_memory(db, entry.id, clock=clock)
    assert used.strength == 1.5
    assert used.last_used_at == clock.now
    assert events[-1].used_memory_ids == [entry.id]
    assert all(
        any(segment.name == "memory" for segment in trace.segments)
        for trace in list_traces(db, conversation.id)
    )
