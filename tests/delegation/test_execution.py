# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Serial child graphs preserve capability, budget, history and correlation boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, send_message
from datakeel.core.agent_models import (
    ConversationCreate,
    MessageInput,
    ModelResponse,
    ScriptedResponse,
    ToolCall,
)
from datakeel.core.harness_models import TokenUsage
from datakeel.core.models import JsonDocument
from datakeel.delegation.service import delegate
from datakeel.delegation.tree import call_tree
from datakeel.harness.service import list_accounts, list_traces
from datakeel.storage import conversation_store as memory
from datakeel.storage.checkpoint_store import CheckpointQuery, list_checkpoints
from datakeel.storage.conversation_authorization import list_audit
from datakeel.storage.dataset_service import import_paths

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.agent_models import Conversation
    from datakeel.delegation.models import ChildResult
    from datakeel.storage.database import Database


def search(agent: str = "main") -> ScriptedResponse:
    """Discover delegation independently within the current isolated conversation."""
    return ScriptedResponse(
        agent=agent,
        tool_calls=[
            ToolCall(name="tool_search", arguments=JsonDocument({"query": "delegate_agent"}))
        ],
    )


def request(agent: str = "main", name: str = "catalog-analyst") -> ScriptedResponse:
    """Ask the registered catalog specialist to inspect its own task."""
    return ScriptedResponse(
        agent=agent,
        tool_calls=[
            ToolCall(
                name="delegate_agent", arguments=JsonDocument({"agent": name, "task": "child task"})
            )
        ],
    )


def test_catalog_delegation_isolated_history_billing_and_replay(db: Database) -> None:
    """Share root billing while keeping transcript and checkpoint threads apart."""
    root = create_conversation(db, ConversationCreate())
    call = request()
    fake = FakeProvider(
        [
            search(),
            call,
            ScriptedResponse(agent="catalog-analyst", tool_calls=[ToolCall(name="list_datasets")]),
            ScriptedResponse(agent="catalog-analyst", content="child conclusion"),
            ScriptedResponse(agent="main", content="parent answer"),
        ]
    )
    events = list(
        send_message(db, root.id, MessageInput(content="parent-only request"), provider=fake)
    )
    tree = call_tree(db, root.id)
    child = memory.get(db, tree.nodes[1].id)
    assert len(tree.nodes) == 2
    assert len(tree.traces) == 5
    assert memory.get(db, root.id).turns == 3
    assert child.turns == 2
    assert len(memory.list_all(db)) == 1
    assert "parent-only request" not in " ".join(item.content for item in child.messages)
    assert all(trace.accounting_conversation_id == root.id for trace in tree.traces if trace.depth)
    assert all(
        trace.parent_tool_call_id == call.tool_calls[0].id for trace in tree.traces if trace.depth
    )
    assert {
        record.key.thread_id
        for node in tree.nodes
        for record in list_checkpoints(db, CheckpointQuery(thread_id=node.id))
    } == {root.id, child.id}
    assert [event.call.name for event in events if event.call] == [
        "tool_search",
        "delegate_agent",
        "list_datasets",
    ]
    assert (
        next(
            event for event in events if event.event == "done" and event.agent_path != "main"
        ).tokens
        > 0
    )
    assert all(
        tool.name in (child.allowed_tools or []) or tool.name == "tool_search"
        for tool in fake.requests[2].tools
    )
    before = list_traces(db, root.id), list_accounts(db)
    replay = delegate(db, memory.get(db, root.id), call.tool_calls[0], 1, _must_not_run)
    assert replay.outcome.content.root["summary"] == "child conclusion"
    assert (list_traces(db, root.id), list_accounts(db)) == before


def _must_not_run(child: Conversation, task: str) -> ChildResult:
    msg = "A completed delegation must never rerun its child"
    raise AssertionError(msg)


def test_child_cannot_call_outside_scope(db: Database, tmp_path: Path) -> None:
    """A fabricated resident read outside the frozen scope is rejected and audited."""
    file = tmp_path / "sample.txt"
    file.write_text("Generated healthy fixture.")
    dataset = import_paths(db, "scope-fixture", [file])
    root = create_conversation(db, ConversationCreate(dataset_id=dataset.id))
    fake = FakeProvider(
        [
            search(),
            request(),
            ModelResponse(
                tool_calls=[
                    ToolCall(name="get_quality", arguments=JsonDocument({"dataset_id": dataset.id}))
                ]
            ),
            ModelResponse(content="denied"),
            ModelResponse(content="parent"),
        ]
    )
    events = list(send_message(db, root.id, MessageInput(content="delegate"), provider=fake))
    result = next(
        event.outcome for event in events if event.outcome and event.outcome.name == "get_quality"
    )
    child = call_tree(db, root.id).nodes[1]
    assert result.status == "FAILED"
    assert result.error == "Tool outside delegated scope"
    assert list_audit(db, child.id)[0].kind == "DELEGATION_DENIED"
    assert "get_quality" not in {tool.name for tool in fake.requests[2].tools}


def test_nested_delegation_cannot_exceed_depth(db: Database) -> None:
    """Depth two can attempt delegation but cannot create or charge a depth-three child."""
    root = create_conversation(db, ConversationCreate())
    fake = FakeProvider(
        [
            search(),
            request(),
            search("catalog-analyst"),
            request("catalog-analyst"),
            search("catalog-analyst"),
            request("catalog-analyst"),
            ModelResponse(content="depth refused"),
            ModelResponse(content="child finished"),
            ModelResponse(content="parent finished"),
        ]
    )
    events = list(send_message(db, root.id, MessageInput(content="delegate"), provider=fake))
    tree = call_tree(db, root.id)
    assert len(tree.nodes) == 3
    assert max(node.depth for node in tree.nodes) == 2
    assert any(
        event.outcome and event.outcome.error == "delegation_depth_exceeded" for event in events
    )
    assert list_audit(db, tree.nodes[-1].id)[0].reason == "delegation_depth_exceeded"


def test_same_reply_fourth_delegation_is_refused_and_queue_stays_serial(db: Database) -> None:
    """Consume three child replies serially before the parent's answer, never a fourth child."""
    root = create_conversation(db, ConversationCreate())
    batch = ModelResponse(
        tool_calls=[
            ToolCall(
                name="delegate_agent",
                arguments=JsonDocument({"agent": "catalog-analyst", "task": f"Task {index}"}),
            )
            for index in range(4)
        ]
    )
    fake = FakeProvider(
        [
            search(),
            batch,
            *[
                ScriptedResponse(agent="catalog-analyst", content=f"child {index}")
                for index in range(3)
            ],
            ScriptedResponse(agent="main", content="parent"),
        ]
    )
    events = list(send_message(db, root.id, MessageInput(content="delegate"), provider=fake))
    assert len(call_tree(db, root.id).nodes) == 4
    assert any(
        event.outcome and event.outcome.error == "delegation_parallel_exceeded" for event in events
    )
    assert fake.script_errors == []
    assert fake.script == []
    assert list_audit(db, root.id)[0].reason == "delegation_parallel_exceeded"


def test_nested_specialist_cannot_expand_parent_scope(db: Database) -> None:
    """A read-only specialist cannot delegate its authority into reversible metric writes."""
    root = create_conversation(db, ConversationCreate())
    fake = FakeProvider(
        [
            search(),
            request(),
            search("catalog-analyst"),
            request("catalog-analyst", "metric-manager"),
            ModelResponse(content="refused"),
            ModelResponse(content="parent"),
        ]
    )
    events = list(send_message(db, root.id, MessageInput(content="delegate"), provider=fake))
    assert len(call_tree(db, root.id).nodes) == 2
    assert any(
        event.outcome and event.outcome.error == "delegation_scope_exceeded" for event in events
    )


def test_child_budget_overrun_stops_entire_root_response(db: Database) -> None:
    """Charge the child to the root and do not consume the pending parent script response."""
    root = create_conversation(db, ConversationCreate())
    fake = FakeProvider(
        [
            search(),
            request(),
            ModelResponse(content="not published", usage=TokenUsage(input_tokens=100001)),
            ModelResponse(content="must not run"),
        ]
    )
    events = list(send_message(db, root.id, MessageInput(content="delegate"), provider=fake))
    assert any(
        event.stop_reason == "budget_exceeded" and event.agent_path == "main" for event in events
    )
    assert len(fake.script) == 1
    assert memory.get(db, root.id).turns == 2
    assert list_traces(db, root.id)[-1].budget_exceeded
