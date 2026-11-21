# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Adaptive prompt history preserves protocol groups and durable action evidence."""

import json
from datetime import UTC, datetime

import pytest

from datakeel.actions.models import ActionContext, ActionImpact, ActionPlan, ActionRun
from datakeel.agent.context import assemble
from datakeel.core.agent_models import (
    ChatMessage,
    Conversation,
    ConversationCreate,
    ToolCall,
    ToolDefinition,
)
from datakeel.core.context_tokens import estimate_tokens
from datakeel.core.envelopes import envelope
from datakeel.core.harness_models import BudgetLimits
from datakeel.core.models import JsonDocument
from datakeel.ontology.models import FrozenManifest, ObjectSet
from datakeel.ontology.tool_history import compact_history
from datakeel.ontology.tool_models import ToolOutcome


def _serialized(messages: list[ChatMessage]) -> str:
    return json.dumps(
        [message.model_dump(mode="json") for message in messages], separators=(",", ":")
    )


def _result(identifier: str, outcome: ToolOutcome | None = None) -> ChatMessage:
    value = outcome or ToolOutcome(
        name="list_datasets", status="SUCCEEDED", content=JsonDocument({"count": 2})
    )
    return ChatMessage(
        role="tool", name=value.name, tool_call_id=identifier, content=value.model_dump_json()
    )


def _call(*identifiers: str) -> ChatMessage:
    return ChatMessage(
        role="assistant",
        tool_calls=[ToolCall(id=identifier, name="list_datasets") for identifier in identifiers],
    )


def _action_results() -> list[ChatMessage]:
    at = datetime(2026, 1, 1, tzinfo=UTC)
    plan = ActionPlan(
        id="plan-retain-123",
        action_type="quarantine_files",
        canonical_params={},
        manifest=FrozenManifest(query=ObjectSet(), objects=[], state_digest="state", total_bytes=0),
        plan_digest="plan",
        target_digest="target",
        state_digest="state",
        created_at=at,
        expires_at=at,
        reversible=True,
        external=False,
        impact=ActionImpact(object_count=0, total_bytes=0, external=False),
        actor="local",
        context=ActionContext(),
    )
    run = ActionRun(
        id="run-retain-456",
        plan_id=plan.id,
        action_type=plan.action_type,
        status="SUCCEEDED",
        created_at=at,
    )
    return [
        _call("plan-call"),
        _result("plan-call", ToolOutcome(name="prepare_plan", status="SUCCEEDED", plan=plan)),
        _call("run-call"),
        _result("run-call", ToolOutcome(name="execute_plan", status="SUCCEEDED", run=run)),
    ]


def _long_history() -> tuple[list[ChatMessage], list[ChatMessage]]:
    messages = [
        ChatMessage(role="system", content="Keep the system policy."),
        ChatMessage(role="system", content="Keep the workspace policy."),
    ]
    for index in range(12):
        messages.extend(
            [
                ChatMessage(role="user", content=f"topic-{index}: " + "detail " * 300),
                _call(f"read-{index}"),
                _result(f"read-{index}"),
            ]
        )
    messages.extend(_action_results())
    messages.extend(
        [
            _call("failed-call"),
            _result("failed-call", ToolOutcome(name="query_kg", status="FAILED", error="No rows")),
        ]
    )
    tail = [
        ChatMessage(role="user", content="Recent question"),
        _call("parallel-a", "parallel-b"),
        _result("parallel-a"),
        _result("parallel-b"),
        ChatMessage(role="assistant", content="Both reads completed."),
        ChatMessage(role="user", content="Follow up"),
        _call("final-call"),
        _result("final-call"),
    ]
    return [*messages, *tail], tail


def test_default_and_inclusive_threshold_preserve_serialized_history() -> None:
    """The optional budget leaves the existing output exactly unchanged until exceeded."""
    messages, _ = _long_history()
    baseline = compact_history(messages, [])
    assert _serialized(baseline) == _serialized(messages)
    for limit in (estimate_tokens(_serialized(baseline)), 1_000_000):
        assert _serialized(compact_history(messages, [], max_history_tokens=limit)) == _serialized(
            baseline
        )


def test_inclusive_threshold_retains_legacy_read_and_discovery_compaction() -> None:
    """A fitting legacy result keeps precisely the same folded reads and pruned schemas."""
    tool = ToolDefinition(
        name="list_datasets",
        description="List datasets",
        parameters=JsonDocument({"type": "object"}),
    )
    messages = [
        _result(
            "old",
            ToolOutcome(
                name=tool.name, status="SUCCEEDED", content=JsonDocument({"text": "x" * 5000})
            ),
        ),
        _result(
            "search",
            ToolOutcome(
                name="tool_search",
                status="SUCCEEDED",
                content=JsonDocument({"tools": [tool.model_dump(mode="json")]}),
            ),
        ),
        *[_result(f"recent-{index}") for index in range(4)],
    ]
    baseline = compact_history(messages, [tool])
    assert ToolOutcome.model_validate_json(baseline[0].content).content.root["folded"] is True
    assert ToolOutcome.model_validate_json(baseline[1].content).content.root == {
        "tools": [{"name": tool.name, "description": tool.description}]
    }
    assert baseline[2:] == messages[2:]
    limited = compact_history(
        messages, [tool], max_history_tokens=estimate_tokens(_serialized(baseline))
    )
    assert _serialized(limited) == _serialized(baseline)


@pytest.mark.parametrize("budget_tokens", [0, 1, 8192])
def test_small_budget_preserves_short_prompt_and_transcript(budget_tokens: int) -> None:
    """Budget-exhausted runs still get their exact short history through the 4096 floor."""
    messages = [ChatMessage(role="user", content="Inspect data"), _call("read"), _result("read")]
    conversation = Conversation(
        id="small-budget",
        config=ConversationCreate(budget=BudgetLimits(conversation_tokens=budget_tokens)),
        messages=messages,
    )
    persisted = conversation.model_dump_json()
    request = assemble(conversation, [], [], JsonDocument({}))
    assert estimate_tokens(_serialized(messages)) < 4096
    assert _serialized(request.messages[1:-1]) == _serialized([envelope(m) for m in messages])
    assert conversation.model_dump_json() == persisted


@pytest.mark.parametrize(("keep_recent", "tail_start"), [(8, 0), (6, 1), (5, 1), (1, 6)])
def test_long_history_summarizes_without_splitting_tool_exchanges(
    keep_recent: int, tail_start: int
) -> None:
    """Summaries retain action IDs and expand a cutoff inside either parallel tool response."""
    messages, tail = _long_history()
    result = compact_history(
        messages, [], max_history_tokens=4096, keep_recent_messages=keep_recent
    )
    assert result == compact_history(
        messages, [], max_history_tokens=4096, keep_recent_messages=keep_recent
    )
    summaries = [message for message in result if message.name == "history_summary"]
    assert len(summaries) == 1
    assert summaries[0].role == "user"
    summary = JsonDocument.model_validate_json(summaries[0].content).root
    assert summary["compacted_messages"] == len(messages) - 2 - len(tail[tail_start:])
    assert isinstance(summary["compacted_turns"], int)
    assert summary["compacted_turns"] >= 12
    topics = summary["topics"]
    assert isinstance(topics, list)
    assert len(topics) <= 4
    assert all(isinstance(topic, str) and len(topic) <= 120 for topic in topics)
    assert len(topics) == len({str(topic) for topic in topics})
    assert "topic-11" in summaries[0].content
    tools = summary["tools"]
    assert isinstance(tools, list)
    assert {"name": "query_kg", "count": 1, "status": "FAILED"} in tools
    reads = 14 if tail_start == 6 else 12
    assert {"name": "list_datasets", "count": reads, "status": "SUCCEEDED"} in tools
    assert summary["plan_ids"] == ["plan-retain-123"]
    assert summary["run_ids"] == ["run-retain-456"]
    assert _serialized(result[:2]) == _serialized(messages[:2])
    assert _serialized(result[3:]) == _serialized(tail[tail_start:])
    calls = {call.id for message in result for call in message.tool_calls}
    assert calls == {message.tool_call_id for message in result if message.role == "tool"}
    assert estimate_tokens(_serialized(result)) < estimate_tokens(_serialized(messages)) // 5


def test_assembly_compacts_only_prompt_and_keeps_persisted_messages() -> None:
    """Repeated assembly stays deterministic without rewriting the conversation object."""
    messages, tail = _long_history()
    conversation = Conversation(
        id="long-history",
        config=ConversationCreate(budget=BudgetLimits(conversation_tokens=8192)),
        messages=messages,
    )
    persisted = conversation.model_dump_json()
    request = assemble(conversation, [], [], JsonDocument({}))
    assert any(message.name == "history_summary" for message in request.messages)
    assert request == assemble(conversation, [], [], JsonDocument({}))
    assert request.messages[-9:-1] == [envelope(message) for message in tail]
    assert conversation.model_dump_json() == persisted


def test_aggressive_read_folding_can_fit_without_a_summary() -> None:
    """A medium old output is folded before discarding any conversational messages."""
    old = _result(
        "read",
        ToolOutcome(
            name="list_datasets", status="SUCCEEDED", content=JsonDocument({"text": "x" * 1500})
        ),
    )
    messages = [_call("read"), old, ChatMessage(role="user", content="Latest request")]
    result = compact_history(messages, [], max_history_tokens=1200, keep_recent_messages=1)
    assert len(result) == len(messages)
    assert result[0] == messages[0]
    assert result[-1] == messages[-1]
    assert ToolOutcome.model_validate_json(result[1].content).content.root["folded"] is True
    assert estimate_tokens(_serialized(result)) <= 1200
    assert all(message.name != "history_summary" for message in result)


def test_protected_history_remains_verbatim_when_no_middle_can_be_compacted() -> None:
    """Even an impossible target cannot consume system messages or the protected tail."""
    messages = [ChatMessage(role="system", content="policy" * 100), _call("read"), _result("read")]
    assert compact_history(messages, [], max_history_tokens=1) == messages
    assert compact_history([], [], max_history_tokens=1) == []


def test_zero_recent_messages_summarizes_entire_non_system_history() -> None:
    """An explicitly empty recent window still preserves the complete system prefix."""
    messages, _ = _long_history()
    result = compact_history(messages, [], max_history_tokens=4096, keep_recent_messages=0)
    assert result[:2] == messages[:2]
    assert len(result) == 3
    assert result[2].name == "history_summary"


def test_summary_selects_recent_distinct_topics_and_normalizes_whitespace() -> None:
    """Repeated questions consume one topic slot and retain their most recent order."""
    messages = [
        ChatMessage(role="user", content=topic)
        for topic in ("old", "alpha", "beta", "gamma", " delta ", "beta\n ")
    ]
    result = compact_history(messages, [], max_history_tokens=1, keep_recent_messages=0)
    summary = JsonDocument.model_validate_json(result[0].content).root
    assert summary["topics"] == ["alpha", "gamma", "delta", "beta"]


def test_protected_tail_restores_large_outputs_folded_by_the_legacy_pass() -> None:
    """All eight protected messages remain verbatim even with more than four recent tools."""
    identifiers = [f"parallel-{index}" for index in range(6)]
    tail = [
        _call(*identifiers),
        *[
            _result(
                identifier,
                ToolOutcome(
                    name="list_datasets",
                    status="SUCCEEDED",
                    content=JsonDocument({"text": "x" * 3000}),
                ),
            )
            for identifier in identifiers
        ],
        ChatMessage(role="user", content="Latest request"),
    ]
    messages = [ChatMessage(role="user", content="Older topic " * 3000), *tail]
    result = compact_history(messages, [], max_history_tokens=4096)
    assert result[0].name == "history_summary"
    assert _serialized(result[1:]) == _serialized(tail)
