# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Concurrent reads preserve live observations, durable order and sequential guard stops."""

from __future__ import annotations

from threading import Barrier, Event, get_ident
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from datakeel.actions.policy import digest
from datakeel.agent.dispatch import ToolDispatcher
from datakeel.agent.guards import LoopGuard
from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, get_conversation, send_message
from datakeel.core.agent_models import (
    ChatMessage,
    ConversationCreate,
    MessageInput,
    ModelResponse,
    ToolCall,
)
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument
from datakeel.ontology import tooling
from datakeel.ontology.models import FunctionResult
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.persistence import migrate
from datakeel.storage import conversation_store as memory
from datakeel.storage.database import Database
from datakeel.storage.tool_invocations import invocation_identity, list_invocations

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.data_asset_models import AccessContext


def _calls() -> list[ToolCall]:
    return [ToolCall(name="list_datasets"), ToolCall(name="search_files")]


def _dispatcher(db: Database, calls: list[ToolCall], guard: LoopGuard) -> ToolDispatcher:
    conversation = create_conversation(db, ConversationCreate())
    lease = memory.begin(db, conversation.id, MessageInput(content="Read available data"))
    memory.append(
        db, conversation.id, lease.token, message=ChatMessage(role="assistant", tool_calls=calls)
    )
    return ToolDispatcher(db, conversation.id, lease.token, guard)


def test_parallel_reads_overlap_and_keep_ordered_transcripts_and_audits(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real persisted reads meet at a barrier and finish in reverse order without reordering UI."""
    calls, barrier, second_done = _calls(), Barrier(2, timeout=3), Event()
    invoke = tooling.invoke_function
    completed: list[str] = []

    def synchronized(
        database: Database, name: str, arguments: JsonDocument, *, access: AccessContext | None
    ) -> FunctionResult:
        barrier.wait()
        result = invoke(database, name, arguments, access=access)
        if name == calls[0].name:
            assert second_done.wait(3)
        completed.append(name)
        if name == calls[1].name:
            second_done.set()
        return result

    monkeypatch.setattr(tooling, "invoke_function", synchronized)
    conversation = create_conversation(db, ConversationCreate())
    request = MessageInput(content="Read available data", mode="agent")
    provider = FakeProvider([ModelResponse(tool_calls=calls), ModelResponse(content="Done")])
    events = list(send_message(db, conversation.id, request, provider=provider))
    assert completed == [call.name for call in reversed(calls)]
    assert [event.event for event in events] == [
        "tool_call",
        "tool_call",
        "tool_result",
        "tool_result",
        "text",
        "done",
    ]
    assert [event.call for event in events[:2]] == calls
    outcomes = [event.outcome for event in events if event.outcome is not None]
    assert [outcome.name for outcome in outcomes] == [call.name for call in calls]
    assert all(outcome.status == "SUCCEEDED" for outcome in outcomes)
    view = get_conversation(db, conversation.id)
    messages = [message for message in view.messages if message.role == "tool"]
    assert [message.tool_call_id for message in messages] == [call.id for call in calls]
    assert [ToolOutcome.model_validate_json(message.content) for message in messages] == outcomes
    invocations = list_invocations(db, conversation.id)
    assert {item.id for item in invocations} == {
        invocation_identity(conversation.id, call.id) for call in calls
    }
    assert all(item.status == "SUCCEEDED" and item.completed_at for item in invocations)
    assert view.events == events
    assert list(send_message(db, conversation.id, request, provider=provider)) == events
    assert list_invocations(db, conversation.id) == invocations


def test_parallel_first_result_streams_while_later_read_is_still_blocked(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first future is observed immediately instead of joining the whole pool before yield."""
    calls, release, second_started, second_done = _calls(), Event(), Event(), Event()
    invoke = tooling.invoke_function

    def blocked(
        database: Database, name: str, arguments: JsonDocument, *, access: AccessContext | None
    ) -> FunctionResult:
        if name == calls[1].name:
            second_started.set()
            assert release.wait(5), "The first result waited for the slower parallel read"
        result = invoke(database, name, arguments, access=access)
        if name == calls[1].name:
            second_done.set()
        return result

    monkeypatch.setattr(tooling, "invoke_function", blocked)
    conversation = create_conversation(db, ConversationCreate())
    stream = send_message(
        db,
        conversation.id,
        MessageInput(content="Read available data", mode="agent"),
        provider=FakeProvider([ModelResponse(tool_calls=calls), ModelResponse(content="Done")]),
    )
    try:
        starts = [next(stream), next(stream)]
        assert [event.call for event in starts] == calls
        first = next(stream)
        assert first.event == "tool_result"
        assert first.outcome is not None
        assert first.outcome.name == calls[0].name
        assert second_started.wait(3)
        assert not second_done.is_set()
    finally:
        release.set()
    remaining = list(stream)
    assert second_done.is_set()
    assert [event.event for event in remaining] == ["tool_result", "text", "done"]


def test_replayed_id_after_parallel_prefix_still_emits_its_start(db: Database) -> None:
    """A later duplicate is streamed sequentially while reusing its original durable invocation."""
    calls = _calls()
    calls.append(calls[0])
    conversation = create_conversation(db, ConversationCreate())
    with patch.object(tooling, "invoke_function", wraps=tooling.invoke_function) as invoked:
        events = list(
            send_message(
                db,
                conversation.id,
                MessageInput(content="Read available data", mode="agent"),
                provider=FakeProvider(
                    [ModelResponse(tool_calls=calls), ModelResponse(content="Done")]
                ),
            )
        )
        assert invoked.call_count == 2
    assert [event.event for event in events] == [
        "tool_call",
        "tool_call",
        "tool_result",
        "tool_result",
        "tool_call",
        "tool_result",
        "text",
        "done",
    ]
    assert [event.call for event in events if event.event == "tool_call"] == calls
    assert events[2].outcome == events[5].outcome
    view = get_conversation(db, conversation.id)
    assert view.events == events
    assert [message.tool_call_id for message in view.messages if message.role == "tool"] == [
        call.id for call in calls[:2]
    ]
    assert len(list_invocations(db, conversation.id)) == 2


@pytest.mark.parametrize("url", ["sqlite://", "sqlite:///:memory:"])
def test_memory_sqlite_reads_stay_on_the_dispatching_thread(
    url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An actual in-memory store executes sequentially without losing its connection-local data."""
    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path / "home"))
    database, calls, thread_ids = Database(url), _calls(), []
    invoke = tooling.invoke_function

    def observed(
        db: Database, name: str, arguments: JsonDocument, *, access: AccessContext | None
    ) -> FunctionResult:
        thread_ids.append(get_ident())
        return invoke(db, name, arguments, access=access)

    monkeypatch.setattr(tooling, "invoke_function", observed)
    try:
        migrate(database)
        dispatcher = _dispatcher(database, calls, LoopGuard())
        with dispatcher.parallel_reads(calls) as parallel:
            assert parallel == []
            for call in calls:
                events, reason = dispatcher.dispatch(call, dry_run=False)
                assert reason is None
                assert events[0].outcome is not None
                assert events[0].outcome.status == "SUCCEEDED"
        assert thread_ids == [get_ident(), get_ident()]
        assert len(list_invocations(database, dispatcher.conversation_id)) == 2
    finally:
        database.engine.dispose()


def _guard(reason: str, calls: list[ToolCall]) -> LoopGuard:
    guard = LoopGuard()
    signature = digest({"name": calls[0].name, "arguments": calls[0].arguments.root})
    if reason == "repeated_call":
        guard.calls[signature] = 2
    elif reason == "ping_pong":
        guard.history = ["other", signature, "other"]
    elif reason == "tool_failures":
        guard.failures[calls[0].name] = 2
    else:
        guard.last_result = digest({"function": calls[0].name, "asset_refs": [], "data": []})
        guard.no_progress = 2
    return guard


@pytest.mark.parametrize("reason", ["repeated_call", "ping_pong", "tool_failures", "no_progress"])
def test_guard_stops_never_speculatively_execute_later_reads(
    db: Database, monkeypatch: pytest.MonkeyPatch, reason: str
) -> None:
    """Every independent sequential stopping rule prevents a later call from entering a worker."""
    calls = [
        ToolCall(name="list_datasets", arguments=JsonDocument({"limit": limit})) for limit in (1, 2)
    ]
    invoked: list[str] = []

    def observed(
        database: Database, name: str, arguments: JsonDocument, *, access: AccessContext | None
    ) -> FunctionResult:
        invoked.append(name)
        if reason == "tool_failures":
            msg = "Fixture read failure"
            raise ValidationError(msg)
        return FunctionResult(function=name, asset_refs=[], data=[])

    monkeypatch.setattr(tooling, "invoke_function", observed)
    dispatcher = _dispatcher(db, calls, _guard(reason, calls))
    with dispatcher.parallel_reads(calls) as parallel:
        assert parallel == []
        _events, stop = dispatcher.dispatch(calls[0], dry_run=False)
        assert stop == reason
    expected = 0 if reason in {"repeated_call", "ping_pong"} else 1
    assert len(invoked) == expected
    assert len(list_invocations(db, dispatcher.conversation_id)) == expected


def test_worker_exception_clears_dispatcher_futures_before_next_batch(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed read cannot leave a future available to a later turn or dispatcher batch."""
    calls, barrier = _calls(), Barrier(2, timeout=3)
    invoke = tooling.invoke_function

    def failing(
        database: Database, name: str, arguments: JsonDocument, *, access: AccessContext | None
    ) -> FunctionResult:
        barrier.wait()
        if name == calls[0].name:
            msg = "Fixture worker failure"
            raise RuntimeError(msg)
        return invoke(database, name, arguments, access=access)

    monkeypatch.setattr(tooling, "invoke_function", failing)
    dispatcher = _dispatcher(db, calls, LoopGuard())
    with (
        pytest.raises(RuntimeError, match="Fixture worker failure"),
        dispatcher.parallel_reads(calls),
    ):
        dispatcher.dispatch(calls[0], dry_run=False)
    monkeypatch.setattr(tooling, "invoke_function", invoke)
    with patch.object(dispatcher.catalog, "invoke", wraps=dispatcher.catalog.invoke) as retried:
        events, reason = dispatcher.dispatch(calls[1], dry_run=False)
        retried.assert_called_once()
    assert reason is None
    assert events[0].outcome is not None
    assert events[0].outcome.status == "SUCCEEDED"
    assert {item.status for item in list_invocations(db, dispatcher.conversation_id)} == {
        "SUCCEEDED",
        "FAILED",
    }
