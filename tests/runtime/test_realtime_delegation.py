# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Cached child progress retains the same ordering as a newly executing delegation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, send_message
from datakeel.core.agent_models import ConversationCreate, MessageInput, ModelResponse
from datakeel.delegation.tree import call_tree
from datakeel.harness.service import list_traces
from tests.delegation.test_execution import request, search

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_cached_delegation_yields_child_history_before_parent_tool_result(db: Database) -> None:
    """Reusing a call streams its stored child events once without rerunning or recharging it."""
    root = create_conversation(db, ConversationCreate())
    call = request()
    initial = list(
        send_message(
            db,
            root.id,
            MessageInput(content="delegate"),
            provider=FakeProvider(
                [
                    search(),
                    call,
                    ModelResponse(content="Child result"),
                    ModelResponse(content="First parent answer"),
                ]
            ),
        )
    )
    child_events = [event for event in initial if event.agent_path != "main"]
    child = call_tree(db, root.id).nodes[1]
    traces = list_traces(db, child.id)
    provider = FakeProvider([call, ModelResponse(content="Reused child result")])
    replay = list(
        send_message(
            db, root.id, MessageInput(content="Use that conclusion again"), provider=provider
        )
    )
    assert replay[0].event == "tool_call"
    assert replay[0].call == call.tool_calls[0]
    assert replay[1 : 1 + len(child_events)] == child_events
    parent_result = replay[1 + len(child_events)]
    assert parent_result.event == "tool_result"
    assert parent_result.outcome is not None
    assert parent_result.outcome.name == "delegate_agent"
    assert len({event.id for event in replay}) == len(replay)
    assert list_traces(db, child.id) == traces
    assert len(call_tree(db, root.id).nodes) == 2
    assert len(provider.requests) == 2
