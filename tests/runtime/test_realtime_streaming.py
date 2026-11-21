# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Live observations precede completion without entering durable transcripts or leaking secrets."""

from __future__ import annotations

from threading import Event
from typing import TYPE_CHECKING

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessageChunk
from langchain_openai import ChatOpenAI

from datakeel.agent.dispatch import ToolDispatcher
from datakeel.agent.providers import FakeProvider
from datakeel.agent.service import create_conversation, get_conversation, send_message
from datakeel.core.agent_models import (
    ConversationCreate,
    MessageInput,
    ModelRequest,
    ModelResponse,
    ToolCall,
)
from datakeel.core.errors import ProviderError
from datakeel.core.harness_models import TokenUsage
from datakeel.delegation.service import delegate
from datakeel.delegation.tree import call_tree
from datakeel.harness.service import list_traces
from datakeel.runtime.chat import ChatProvider, ScriptedChatModel
from datakeel.storage import conversation_store as memory
from datakeel.storage.checkpoint_store import CheckpointQuery, list_checkpoints
from datakeel.storage.conversation_authorization import list_audit
from datakeel.storage.conversation_secrets import get_canary
from tests.delegation.test_execution import request as delegation_request
from tests.delegation.test_execution import search
from tests.routing.protocol_helpers import configure_fallback

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from datakeel.agent.models import AgentEvent
    from datakeel.core.agent_models import Conversation
    from datakeel.delegation.models import ChildResult
    from datakeel.ontology.tool_models import ToolOutcome
    from datakeel.storage.database import Database


class StreamingProvider(ChatProvider):
    """Supply deterministic callbacks through the same runtime adapter as vendor models."""

    def __init__(
        self, invoke: Callable[[ModelRequest, Callable[[str], None] | None], ModelResponse]
    ) -> None:
        """Retain only an ephemeral callback and an offline backing model."""
        super().__init__(ScriptedChatModel(FakeProvider([])))
        self.invoke = invoke

    def complete(
        self, request: ModelRequest, *, on_text_delta: Callable[[str], None] | None = None
    ) -> ModelResponse:
        """Expose a live callback without changing the original fixture provider protocol."""
        return self.invoke(request, on_text_delta)


@pytest.mark.parametrize("model_type", [ChatOpenAI, ChatAnthropic])
def test_chat_provider_streams_text_and_joins_tool_arguments_and_exact_usage(
    monkeypatch: pytest.MonkeyPatch, model_type: type[ChatOpenAI | ChatAnthropic]
) -> None:
    """Both vendors publish nonempty text while retaining split calls and final billing."""
    deltas: list[str] = []

    def stream(_model: object, _input: object, **kwargs: object) -> Iterator[AIMessageChunk]:
        assert kwargs["stream_usage"] is True
        yield AIMessageChunk(content="Hello ")
        assert deltas == ["Hello "]
        yield AIMessageChunk(
            content="world",
            tool_call_chunks=[{"name": "list_datasets", "args": "{", "id": "c", "index": 0}],
        )
        yield AIMessageChunk(content="", tool_call_chunks=[{"args": "}", "index": 0}])
        yield AIMessageChunk(
            content="",
            response_metadata={"finish_reason": "tool_calls"},
            usage_metadata={
                "input_tokens": 31,
                "output_tokens": 9,
                "total_tokens": 40,
                "input_token_details": {"cache_read": 7, "cache_creation": 3},
            },
        )

    monkeypatch.setattr(model_type, "stream", stream)
    model = model_type.model_construct()
    provider = ChatProvider(model)
    request = ModelRequest(model="fixture-model", messages=[], tools=[], segments=[])
    response = provider.complete(request, on_text_delta=deltas.append)
    assert deltas == ["Hello ", "world"]
    assert response.content == "Hello world"
    assert response.tool_calls == [ToolCall(id="c", name="list_datasets")]
    assert response.usage == TokenUsage(
        input_tokens=31, output_tokens=9, cache_read_tokens=7, cache_write_tokens=3
    )
    assert response.usage_known
    assert response.stop_reason == "tool_calls"


def test_json_provider_stream_is_private_even_when_callback_is_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Planner JSON is joined privately and never appears as conversational text deltas."""

    def stream(
        _model: object, _input: object, _config: object = None, **_kwargs: object
    ) -> Iterator[AIMessageChunk]:
        yield AIMessageChunk(content='{"kind": "none"}')

    monkeypatch.setattr(ChatOpenAI, "stream", stream)
    provider = ChatProvider(ChatOpenAI.model_construct())
    request = ModelRequest(
        model="fixture-model", messages=[], tools=[], segments=[], json_output=True
    )
    deltas: list[str] = []
    assert provider.complete(request, on_text_delta=deltas.append).content == '{"kind": "none"}'
    assert deltas == []


def test_text_delta_arrives_before_provider_returns_and_is_never_persisted(db: Database) -> None:
    """A blocked model can already be read, while replay contains authoritative events only."""
    release, returned = Event(), Event()
    content = "A safe answer is already appearing while the model continues. " * 3

    def invoke(_request: ModelRequest, emit: Callable[[str], None] | None) -> ModelResponse:
        assert emit is not None
        emit(content)
        assert release.wait(5), "Consumer did not receive the live delta before model completion"
        returned.set()
        return ModelResponse(content=content)

    conversation = create_conversation(db, ConversationCreate())
    request = MessageInput(content="Explain available data", mode="agent")
    provider = StreamingProvider(invoke)
    stream = send_message(db, conversation.id, request, provider=provider)
    try:
        first = next(stream)
        assert first.event == "text_delta"
        assert first.text
        assert first.agent_path == first.agent_name == "main"
        assert first.conversation_id == conversation.id
        assert not returned.is_set()
    finally:
        release.set()
    events = [first, *stream]
    assert "".join(event.text or "" for event in events if event.event == "text_delta") == content
    authoritative = [event for event in events if event.event != "text_delta"]
    assert get_conversation(db, conversation.id).events == authoritative
    assert list(send_message(db, conversation.id, request, provider=provider)) == authoritative
    assert [event.event for event in authoritative] == ["text", "done"]
    for record in list_checkpoints(db, CheckpointQuery(thread_id=conversation.id)):
        assert b"text_delta" not in record.checkpoint
        assert all(b"text_delta" not in write.value for write in record.writes)


@pytest.mark.parametrize("kind", ["full", "fragment", "obfuscated"])
def test_streaming_canary_never_releases_secret_characters_and_is_audited(
    db: Database, kind: str
) -> None:
    """Previously safe prose may stream; zero characters from a later leak reach the reader."""
    conversation = create_conversation(db, ConversationCreate())
    canary = get_canary(db, conversation.id)
    secret = canary if kind == "full" else canary[4:20]
    if kind == "obfuscated":
        secret = " \n\t".join(secret.upper())
    prefix = "This public introduction is safe to stream. " * 3
    content = prefix + secret

    def invoke(_request: ModelRequest, emit: Callable[[str], None] | None) -> ModelResponse:
        assert emit is not None
        for character in content:
            emit(character)
        return ModelResponse(content=content)

    events = list(
        send_message(
            db, conversation.id, MessageInput(content="Explain"), provider=StreamingProvider(invoke)
        )
    )
    emitted = "".join(event.text or "" for event in events if event.event == "text_delta")
    assert emitted
    assert prefix.startswith(emitted)
    assert [event.event for event in events if event.event != "text_delta"] == ["stopped", "done"]
    assert events[-2].stop_reason == "canary_leak"
    assert [entry.kind for entry in list_audit(db, conversation.id)] == ["CANARY_LEAK"]
    view = get_conversation(db, conversation.id)
    assert [message.role for message in view.messages] == ["user"]
    assert all(event.event != "text_delta" for event in view.events)
    assert canary not in view.model_dump_json()
    assert len(list_traces(db, conversation.id)) == 1


def test_tool_call_and_each_result_arrive_before_the_next_tool_finishes(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A blocked tool exposes its start, and one completed result does not wait for its batch."""
    calls = [ToolCall(name="list_datasets"), ToolCall(name="list_datasets")]
    releases = {call.id: Event() for call in calls}
    completed: list[str] = []
    dispatch = ToolDispatcher.dispatch

    def blocked(
        dispatcher: ToolDispatcher,
        call: ToolCall,
        *,
        dry_run: bool,
        local: Callable[[ToolCall], ToolOutcome] | None = None,
    ) -> tuple[list[AgentEvent], str | None]:
        assert releases[call.id].wait(5), "Tool observations were held until the batch completed"
        result = dispatch(dispatcher, call, dry_run=dry_run, local=local)
        completed.append(call.id)
        return result

    monkeypatch.setattr(ToolDispatcher, "dispatch", blocked)
    conversation = create_conversation(db, ConversationCreate())
    stream = send_message(
        db,
        conversation.id,
        MessageInput(content="List available data"),
        provider=FakeProvider([ModelResponse(tool_calls=calls), ModelResponse(content="Done")]),
    )
    try:
        first = next(stream)
        assert first.call == calls[0]
        assert completed == []
        releases[calls[0].id].set()
        result = next(stream)
        assert result.event == "tool_result"
        assert completed == [calls[0].id]
        second = next(stream)
        assert second.call == calls[1]
        assert completed == [calls[0].id]
    finally:
        for release in releases.values():
            release.set()
    events = [first, result, second, *stream]
    assert [event.event for event in events] == [
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "text",
        "done",
    ]
    assert len({event.id for event in events}) == len(events)


def _must_not_run(_child: Conversation, _task: str) -> ChildResult:
    msg = "A completed child must replay without executing"
    raise AssertionError(msg)


def test_delegated_progress_streams_before_parent_result_and_replays_without_deltas(
    db: Database,
) -> None:
    """Child tools, text and completion retain their path and are delivered only once."""
    release = Event()
    content = "A child answer arrives before its parent tool has finished. " * 2
    call = delegation_request()
    fake = FakeProvider(
        [
            search(),
            call,
            ModelResponse(tool_calls=[ToolCall(name="list_datasets")]),
            ModelResponse(content=content),
            ModelResponse(content="Parent answer"),
        ]
    )

    def invoke(request: ModelRequest, emit: Callable[[str], None] | None) -> ModelResponse:
        response = fake.complete(request)
        if response.content == content:
            assert emit is not None
            emit(content)
            assert release.wait(5), "Child delta was held until parent delegation finished"
        return response

    root = create_conversation(db, ConversationCreate())
    request = MessageInput(content="delegate", mode="agent")
    stream = send_message(db, root.id, request, provider=StreamingProvider(invoke))
    events: list[AgentEvent] = []
    try:
        for event in stream:
            events.append(event)
            if event.event == "text_delta":
                break
        assert events[-1].event == "text_delta"
        assert events[-1].agent_path != "main"
        assert not any(event.outcome and event.outcome.name == "delegate_agent" for event in events)
        assert [event.event for event in events if event.agent_path != "main"] == [
            "tool_call",
            "tool_result",
            "text_delta",
        ]
    finally:
        release.set()
    events.extend(stream)
    _assert_delegation_history(db, root.id, request, call.tool_calls[0], events)


def _assert_delegation_history(
    db: Database, root_id: str, request: MessageInput, call: ToolCall, events: list[AgentEvent]
) -> None:
    child = call_tree(db, root_id).nodes[1]
    child_events = [event for event in events if event.agent_path != "main"]
    assert all(event.conversation_id == child.id for event in child_events)
    assert all(event.agent_name == "catalog-analyst" for event in child_events)
    assert len({event.id for event in events}) == len(events)
    child_done = next(index for index, event in enumerate(events) if event == child_events[-1])
    parent_result = next(
        index
        for index, event in enumerate(events)
        if event.outcome and event.outcome.name == "delegate_agent"
    )
    assert child_events[-1].event == "done"
    assert child_done < parent_result
    for conversation_id in (root_id, child.id):
        assert all(
            event.root["event"] != "text_delta" for event in memory.get(db, conversation_id).events
        )
    replay = list(send_message(db, root_id, request, provider=FakeProvider([])))
    assert replay == [event for event in events if event.event != "text_delta"]
    delegated = delegate(db, memory.get(db, root_id), call, 1, _must_not_run)
    assert all(event.root["event"] != "text_delta" for event in delegated.events)


def test_child_stream_blocks_an_ancestor_canary_before_any_secret_is_emitted(db: Database) -> None:
    """The same holdback applies to ancestor sentinels absent from the child's own prompt."""
    root = create_conversation(db, ConversationCreate())
    canary = get_canary(db, root.id)
    fake = FakeProvider([search(), delegation_request(), ModelResponse(content=canary)])

    def invoke(request: ModelRequest, emit: Callable[[str], None] | None) -> ModelResponse:
        response = fake.complete(request)
        if response.content:
            assert emit is not None
            for character in response.content:
                emit(character)
        return response

    events = list(
        send_message(
            db, root.id, MessageInput(content="delegate"), provider=StreamingProvider(invoke)
        )
    )
    child = call_tree(db, root.id).nodes[1]
    assert not any(event.event == "text_delta" for event in events)
    assert any(
        event.agent_path == child.agent_path and event.stop_reason == "canary_leak"
        for event in events
    )
    assert [entry.kind for entry in list_audit(db, child.id)] == ["CANARY_LEAK"]
    assert canary not in memory.get(db, child.id).model_dump_json()


def test_retry_starts_with_fresh_holdback_and_keeps_failed_tail_private(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A retry cannot flush text still held from a failed provider attempt."""
    config, _settings, backup = configure_fallback(tmp_path, monkeypatch, "openai")
    root = create_conversation(db, config)
    attempts: list[str] = []
    content = "The backup provides a clean answer with independently checked streaming text."

    def invoke(request: ModelRequest, emit: Callable[[str], None] | None) -> ModelResponse:
        assert emit is not None
        attempts.append(request.model)
        if len(attempts) == 1:
            emit("failed private tail")
            msg = "timeout"
            raise ProviderError(msg)
        emit(content)
        return ModelResponse(content=content, usage=TokenUsage(input_tokens=5, output_tokens=7))

    events = list(
        send_message(
            db, root.id, MessageInput(content="Explain"), provider=StreamingProvider(invoke)
        )
    )
    assert len(attempts) == 2
    assert attempts[-1] == backup
    assert "".join(event.text or "" for event in events if event.event == "text_delta") == content
    assert next(event.text for event in events if event.event == "text") == content
    assert len(list_traces(db, root.id)) == 2
