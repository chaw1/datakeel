# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Concurrent specialists retain live progress, ordered results and safety boundaries."""

from __future__ import annotations

from threading import Barrier, Event, Lock
from typing import TYPE_CHECKING

import pytest

from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, send_message
from datakeel.core.agent_models import (
    ConversationCreate,
    MessageInput,
    ModelRequest,
    ModelResponse,
    ScriptedResponse,
    ToolCall,
)
from datakeel.core.harness_models import TokenUsage
from datakeel.core.models import JsonDocument
from datakeel.delegation.models import DelegationResult
from datakeel.delegation.tree import call_tree
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.runtime.chat import ChatProvider, ScriptedChatModel
from datakeel.runtime.graph import AgentGraph
from datakeel.storage import conversation_store as memory
from datakeel.storage.checkpoint_store import CheckpointQuery, list_checkpoints
from datakeel.storage.conversation_authorization import list_audit
from datakeel.storage.conversation_secrets import get_canary
from tests.delegation.test_execution import search

if TYPE_CHECKING:
    from collections.abc import Callable

    from datakeel.agent.models import AgentEvent
    from datakeel.core.agent_models import Conversation
    from datakeel.delegation.service import ChildRunner
    from datakeel.storage.database import Database

SPECIALISTS = ("production-ops", "training-auditor")
USAGE = TokenUsage(input_tokens=7, output_tokens=5)


def _batch(names: tuple[str, str] = SPECIALISTS) -> ModelResponse:
    return ModelResponse(
        tool_calls=[
            ToolCall(
                name="delegate_agent",
                arguments=JsonDocument({"agent": name, "task": f"Inspect task {index}"}),
            )
            for index, name in enumerate(names)
        ]
    )


class ConcurrentProvider(ChatProvider):
    """Require two live child model invocations before either may return."""

    parallel_safe = True

    def __init__(self, *, leak: str = "", leak_agent: str = SPECIALISTS[0]) -> None:
        """Use a locked parent script and a barrier instead of scheduling assumptions."""
        super().__init__(ScriptedChatModel(FakeProvider([])))
        self.batch = _batch()
        self.responses = [search(), self.batch, ModelResponse(content="Parent complete.")]
        self.barrier = Barrier(2, timeout=3)
        self.release, self.lock = Event(), Lock()
        self.completed: list[str] = []
        self.requests: list[ModelRequest] = []
        self.leak = leak
        self.leak_agent = leak_agent

    def complete(
        self, request: ModelRequest, *, on_text_delta: Callable[[str], None] | None = None
    ) -> ModelResponse:
        """Stream both children while their parent awaits deterministic result consumption."""
        with self.lock:
            self.requests.append(request)
            if request.agent_name == "main":
                return self.responses.pop(0).model_copy(update={"usage": USAGE})
        self.barrier.wait()
        content = (
            self.leak
            if self.leak and request.agent_name == self.leak_agent
            else f"Public progress from {request.agent_name}. " * 8
        )
        assert on_text_delta is not None
        on_text_delta(content)
        assert self.release.wait(5), "Both child streams must arrive before model completion"
        with self.lock:
            self.completed.append(request.agent_path)
        return ModelResponse(content=content, usage=USAGE)


def test_specialists_run_concurrently_and_stream_before_ordered_results(db: Database) -> None:
    """A barrier proves concurrent graphs; consumer release proves genuinely live events."""
    root = create_conversation(db, ConversationCreate())
    provider = ConcurrentProvider()
    request = MessageInput(content="Inspect both domains", mode="agent")
    stream = send_message(db, root.id, request, provider=provider)
    events: list[AgentEvent] = []
    live_paths: set[str] = set()
    try:
        for event in stream:
            events.append(event)
            if event.event == "text_delta":
                live_paths.add(event.agent_path)
            if len(live_paths) == 2:
                break
        assert live_paths == {f"main/{name}#1" for name in SPECIALISTS}
        assert provider.completed == []
        assert not any(e.outcome and e.outcome.name == "delegate_agent" for e in events)
    finally:
        provider.release.set()
    events.extend(stream)
    _assert_parallel_results(db, root.id, provider, events)
    assert list(send_message(db, root.id, request, provider=FakeProvider([]))) == [
        event for event in events if event.event != "text_delta"
    ]


def _assert_parallel_results(
    db: Database, root_id: str, provider: ConcurrentProvider, events: list[AgentEvent]
) -> None:
    parent = [event for event in events if event.agent_path == "main"]
    calls = [event.call for event in parent if event.call and event.call.name == "delegate_agent"]
    results = [e for e in parent if e.outcome and e.outcome.name == "delegate_agent"]
    assert calls == provider.batch.tool_calls
    assert all(parent.index(e) < parent.index(results[0]) for e in parent if e.call in calls)
    assert all(event.outcome and event.outcome.status == "SUCCEEDED" for event in results)
    assert not any(event.stop_reason for event in events)
    assert len({event.id for event in events}) == len(events)
    tree = call_tree(db, root_id)
    assert len(tree.nodes) == 3
    assert len(tree.traces) == 5
    assert tree.total_tokens == 60
    assert [node.tokens for node in tree.nodes] == [36, 12, 12]
    assert [node.model_calls for node in tree.nodes] == [3, 1, 1]
    assert [
        event.outcome.content.root["conversation_id"] for event in results if event.outcome
    ] == [node.id for node in tree.nodes[1:]]
    for node, call in zip(tree.nodes[1:], calls, strict=True):
        assert call is not None
        assert node.agent_path == f"main/{node.agent_name}#1"
        assert node.parent_tool_call_id == call.id
        traces = [trace for trace in tree.traces if trace.conversation_id == node.id]
        assert traces[0].accounting_conversation_id == root_id
        assert traces[0].parent_tool_call_id == call.id
        assert traces[0].accounted_tokens == 12
        child = [event for event in events if event.conversation_id == node.id]
        assert child[-1].event == "done"
        assert child[-1].tokens == 12
        assert all(event.agent_path == node.agent_path for event in child)


@pytest.mark.parametrize(
    ("names", "parallel_safe"),
    [
        (SPECIALISTS, False),
        (("evidence-reviewer", "metric-manager"), True),
        (("catalog-analyst", "catalog-analyst"), True),
    ],
)
def test_unsafe_or_duplicate_specialists_preserve_serial_queue(
    db: Database, monkeypatch: pytest.MonkeyPatch, names: tuple[str, str], *, parallel_safe: bool
) -> None:
    """Each child completes before the next parent call is even announced."""
    provider = FakeProvider(
        [
            search(),
            _batch(names),
            *[
                ScriptedResponse(agent=name, content=f"Child {index}")
                for index, name in enumerate(names)
            ],
            ScriptedResponse(agent="main", content="Parent"),
        ]
    )
    if parallel_safe:
        monkeypatch.setattr(provider, "parallel_safe", True, raising=False)
    root = create_conversation(db, ConversationCreate())
    events = list(send_message(db, root.id, MessageInput(content="Inspect"), provider=provider))
    assert [
        event.event
        for event in events
        if event.agent_path == "main"
        and (
            (event.call and event.call.name == "delegate_agent")
            or (event.outcome and event.outcome.name == "delegate_agent")
        )
    ] == ["tool_call", "tool_result", "tool_call", "tool_result"]
    assert provider.script_errors == provider.script == []
    assert len(call_tree(db, root.id).nodes) == 3
    assert len({node.agent_path for node in call_tree(db, root.id).nodes}) == 3


@pytest.mark.parametrize("leak_agent", SPECIALISTS)
def test_concurrent_ancestor_leak_stops_parent_without_persisting_secret(
    db: Database, leak_agent: str
) -> None:
    """A concurrent child still audits and stops both its own and its ancestor's response."""
    root = create_conversation(db, ConversationCreate())
    canary = get_canary(db, root.id)
    provider = ConcurrentProvider(leak=canary, leak_agent=leak_agent)
    provider.release.set()
    events = list(send_message(db, root.id, MessageInput(content="Inspect"), provider=provider))
    assert any(
        event.agent_path == "main" and event.stop_reason == "canary_leak" for event in events
    )
    assert len(provider.completed) == 2
    assert len(provider.responses) == 1
    assert [entry.kind for entry in list_audit(db, root.id)] == ["CANARY_LEAK"]
    tree = call_tree(db, root.id)
    assert len(tree.nodes) == 3
    assert canary not in tree.model_dump_json()
    leaked_child = next(node for node in tree.nodes if node.agent_name == leak_agent)
    assert [entry.kind for entry in list_audit(db, leaked_child.id)] == ["CANARY_LEAK"]
    assert all(canary not in event.model_dump_json() for event in events)
    for node in tree.nodes:
        assert canary not in memory.get(db, node.id).model_dump_json()
        for checkpoint in list_checkpoints(db, CheckpointQuery(thread_id=node.id)):
            assert canary.encode() not in checkpoint.checkpoint + checkpoint.metadata
            assert all(canary.encode() not in write.value for write in checkpoint.writes)


@pytest.mark.parametrize("gate", ["workflow", "undiscovered"])
def test_runtime_visibility_gates_prevent_child_creation(db: Database, gate: str) -> None:
    """A provider opt-in never bypasses discovery or pending workflow confirmation."""
    root = create_conversation(db, ConversationCreate())
    provider = ConcurrentProvider()
    provider.release.set()
    if gate == "undiscovered":
        provider.responses.pop(0)
    lease = memory.begin(db, root.id, MessageInput(content="Inspect"))
    graph = AgentGraph(db, root.id, lease.token, provider)
    graph.workflow_confirmation_required = gate == "workflow"
    try:
        events = list(graph.run())
    finally:
        memory.finish(db, root.id, lease.token, completed=True)
    assert len(call_tree(db, root.id).nodes) == 1
    assert all(request.agent_name == "main" for request in provider.requests)
    results = [
        event.outcome
        for event in events
        if event.outcome and event.outcome.name == "delegate_agent"
    ]
    assert results
    assert all(result.status == "FAILED" for result in results)
    if gate == "workflow":
        assert results[0].error == "workflow_confirmation_required"


@pytest.mark.parametrize(
    "reasons", [("budget_exceeded", "canary_leak"), ("canary_leak", "budget_exceeded")]
)
def test_submitted_sibling_canary_stop_takes_priority_over_budget(
    db: Database, monkeypatch: pytest.MonkeyPatch, reasons: tuple[str, str]
) -> None:
    """Consume every submitted result and retain a canary stop in either result order."""

    def finished(
        database: Database, parent: Conversation, call: ToolCall, ordinal: int, run: ChildRunner
    ) -> DelegationResult:
        reason = reasons[ordinal - 1]
        return DelegationResult(
            stop_reason=reason,
            outcome=ToolOutcome(
                name=call.name,
                status="FAILED",
                error=reason,
                content=JsonDocument({"call_id": call.id}),
            ),
        )

    monkeypatch.setattr("datakeel.runtime.delegation_graph.delegate", finished)
    batch, unused = _batch(), ModelResponse(content="Must not run")
    provider = FakeProvider([search(), batch, unused])
    monkeypatch.setattr(provider, "parallel_safe", True, raising=False)
    root = create_conversation(db, ConversationCreate())
    events = list(send_message(db, root.id, MessageInput(content="Inspect"), provider=provider))
    results = [
        event.outcome
        for event in events
        if event.outcome and event.outcome.name == "delegate_agent"
    ]
    assert [result.error for result in results] == list(reasons)
    assert [result.content.root["call_id"] for result in results] == [
        call.id for call in batch.tool_calls
    ]
    assert [event.stop_reason for event in events if event.event == "stopped"] == ["canary_leak"]
    assert provider.script == [unused]
    assert len(provider.requests) == 2
