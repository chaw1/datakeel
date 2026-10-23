# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Root reporting and interrupted streams preserve child accounting and ownership."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, get_conversation, send_message
from datakeel.core.agent_models import ConversationCreate, MessageInput, ModelResponse
from datakeel.core.harness_models import TokenUsage
from datakeel.delegation.tree import call_tree
from datakeel.harness.service import list_traces, summarize_costs
from datakeel.storage import conversation_store as memory
from tests.delegation.test_execution import request, search

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_root_cost_summary_includes_children_but_root_routes_exclude_them(db: Database) -> None:
    """Budget-facing cost totals use root identity while parent route observations stay local."""
    root = create_conversation(db, ConversationCreate())
    fake = FakeProvider(
        [search(), request(), ModelResponse(content="child"), ModelResponse(content="parent")]
    )
    events = list(send_message(db, root.id, MessageInput(content="delegate"), provider=fake))
    traces = list_traces(db, root.id)
    costs = summarize_costs(db)
    assert len(costs) == 1
    assert costs[0].key == root.id
    assert costs[0].calls == len(traces) == 4
    assert costs[0].input_tokens == sum(trace.usage.input_tokens for trace in traces)
    assert len(events[-1].model_routes) == 3


def test_closing_after_child_done_does_not_complete_parent_request(db: Database) -> None:
    """A transport interruption before the root answer must retain interrupted root ownership."""
    root = create_conversation(db, ConversationCreate())
    fake = FakeProvider(
        [search(), request(), ModelResponse(content="child"), ModelResponse(content="parent")]
    )
    stream = send_message(db, root.id, MessageInput(content="delegate"), provider=fake)
    for event in stream:
        if event.event == "done" and event.agent_path != "main":
            break
    stream.close()
    view = get_conversation(db, root.id)
    assert view.events[-2].stop_reason == "interrupted"
    assert view.events[-1].event == "done"
    assert len(fake.script) == 1


def test_child_reservation_uses_remaining_root_budget_before_calling_provider(db: Database) -> None:
    """Reject a child's first reservation without consuming its script when root funds run low."""
    root = create_conversation(db, ConversationCreate())
    fake = FakeProvider(
        [
            search().model_copy(update={"usage": TokenUsage(input_tokens=1)}),
            request().model_copy(update={"usage": TokenUsage(input_tokens=99000)}),
            ModelResponse(content="must not run"),
        ]
    )
    events = list(send_message(db, root.id, MessageInput(content="delegate"), provider=fake))
    tree = call_tree(db, root.id)
    assert len(tree.nodes) == 2
    assert len(tree.traces) == 2
    assert len(fake.script) == 1
    assert memory.get(db, tree.nodes[1].id).turns == 0
    assert any(
        event.stop_reason == "budget_exceeded" and event.agent_path == "main" for event in events
    )
