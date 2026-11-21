# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep discovery schemas and large read history compact only at the prompt boundary."""

import json
from collections import Counter
from collections.abc import Sequence

from pydantic import JsonValue, ValidationError

from datakeel.core.agent_models import ChatMessage, ToolDefinition
from datakeel.core.context_tokens import estimate_tokens
from datakeel.core.models import JsonDocument
from datakeel.ontology.tool_models import ToolOutcome

_PREVIEW_DEPTH = 2
_HISTORY_TOPIC_CHARS = 120
_HISTORY_TOPIC_COUNT = 4

DEFERRED_READ_FUNCTIONS = frozenset(
    {
        "ask_data",
        "list_metrics",
        "explain_metric",
        "impact_of",
        "query_kg",
        "explain_relation",
        "query_standard_coverage",
        "list_standard_usage",
        "list_quality_rules",
        "get_table_quality",
        "annotation_quality",
        "training_distribution",
        "training_leakage",
        "get_training_quality",
        "project_progress",
        "package_status",
        "annotator_workload",
        "rework_rate",
        "annotation_consistency",
        "prelabel_confidence",
        "label_set_diff",
        "next_task",
        "production_objects",
        "production_prelabel_accuracy",
        "lease_status",
        "skill_workload",
        "package_acceptance",
        "assignees",
    }
)


def compact_tool_search(
    message: ChatMessage, loaded_tools: Sequence[ToolDefinition]
) -> ChatMessage:
    """Drop parameter schemas that the request already declares as native tool definitions."""
    if message.role != "tool" or message.name != "tool_search":
        return message
    try:
        outcome = ToolOutcome.model_validate_json(message.content)
    except ValidationError:
        return message
    definitions = outcome.content.root.get("tools")
    if not isinstance(definitions, list):
        return message
    loaded = [json.dumps(tool.model_dump(mode="json"), sort_keys=True) for tool in loaded_tools]
    content: dict[str, JsonValue] = {
        **{
            key: value
            for key, value in outcome.content.root.items()
            if outcome.content.root.get("truncated") is True
            or key not in {"total_matches", "truncated"}
        },
        "tools": [
            {key: value for key, value in item.items() if key != "parameters"}
            if isinstance(item, dict) and json.dumps(item, sort_keys=True) in loaded
            else item
            for item in definitions
        ],
    }
    outcome = outcome.model_copy(update={"content": JsonDocument(content)})
    return message.model_copy(update={"content": outcome.model_dump_json()})


def compact_history(
    messages: Sequence[ChatMessage],
    loaded_tools: Sequence[ToolDefinition],
    *,
    keep_recent_tools: int = 4,
    max_tool_bytes: int = 2048,
    max_history_tokens: int | None = None,
    keep_recent_messages: int = 8,
) -> list[ChatMessage]:
    """Fold older read output without modifying persisted messages or recent tool exchanges."""
    compacted = [compact_tool_search(message, loaded_tools) for message in messages]
    candidates = [
        index
        for index, message in enumerate(compacted)
        if message.role == "tool" and message.name != "tool_search"
    ]
    older = candidates[:-keep_recent_tools] if keep_recent_tools > 0 else candidates
    for index in older:
        compacted[index] = _fold_read(compacted[index], max_tool_bytes)
    if max_history_tokens is None or _history_tokens(compacted) <= max_history_tokens:
        return compacted
    prefix, split = _history_boundary(messages, keep_recent_messages)
    # Adaptive compaction protects the original tail, including discovery and large reads.
    compacted[:prefix], compacted[split:] = messages[:prefix], messages[split:]
    for index in range(prefix, split):
        if compacted[index].role == "tool":
            compacted[index] = _fold_read(compacted[index], 256)
    if prefix == split or _history_tokens(compacted) <= max_history_tokens:
        return compacted
    return [*compacted[:prefix], _history_summary(messages[prefix:split]), *compacted[split:]]


def _history_tokens(messages: Sequence[ChatMessage]) -> int:
    return estimate_tokens(
        json.dumps([message.model_dump(mode="json") for message in messages], separators=(",", ":"))
    )


def _history_boundary(messages: Sequence[ChatMessage], keep_recent: int) -> tuple[int, int]:
    prefix = 0
    while prefix < len(messages) and messages[prefix].role == "system":
        prefix += 1
    split = max(prefix, len(messages) - max(0, keep_recent))
    responses = {
        message.tool_call_id: index
        for index, message in enumerate(messages)
        if message.role == "tool" and message.tool_call_id is not None
    }
    # Walk backward so expanding across one exchange also protects any earlier crossing one.
    for index in range(split - 1, prefix - 1, -1):
        message = messages[index]
        if message.role == "assistant" and any(
            responses.get(call.id, -1) >= split for call in message.tool_calls
        ):
            split = index
    return prefix, split


def _history_summary(messages: Sequence[ChatMessage]) -> ChatMessage:
    tools: Counter[tuple[str, str]] = Counter()
    plans: set[str] = set()
    runs: set[str] = set()
    for message in messages:
        if message.role != "tool":
            continue
        try:
            content = JsonDocument.model_validate_json(message.content).root
        except ValidationError:
            content = {}
        status = content.get("status")
        status = str(status) if status in ("SUCCEEDED", "FAILED") else "UNKNOWN"
        name = message.name or content.get("name")
        tools[(name if isinstance(name, str) else "unknown", status)] += 1
        _history_action_ids(content, plans, runs)
    summary: dict[str, JsonValue] = {
        "compacted_messages": len(messages),
        "compacted_turns": sum(message.role == "user" for message in messages),
        "topics": [*_history_topics(messages)],
        "tools": [
            {"name": name, "count": count, "status": status}
            for (name, status), count in sorted(tools.items())
        ],
        "plan_ids": [*sorted(plans)],
        "run_ids": [*sorted(runs)],
    }
    return ChatMessage(
        role="user",
        name="history_summary",
        content=json.dumps(summary, ensure_ascii=False, separators=(",", ":")),
    )


def _history_topics(messages: Sequence[ChatMessage]) -> list[str]:
    topics: list[str] = []
    for message in reversed(messages):
        if message.role != "user":
            continue
        topic = " ".join(message.content.split())
        if len(topic) > _HISTORY_TOPIC_CHARS:
            topic = topic[: _HISTORY_TOPIC_CHARS - 3].rstrip() + "..."
        if topic and topic not in topics:
            topics.append(topic)
        if len(topics) == _HISTORY_TOPIC_COUNT:
            break
    return list(reversed(topics))


def _history_action_ids(value: JsonValue, plans: set[str], runs: set[str]) -> None:
    if isinstance(value, list):
        for item in value:
            _history_action_ids(item, plans, runs)
    elif isinstance(value, dict):
        for key, item in value.items():
            target = plans if key in {"plan", "plan_id", "plan_ids"} else runs
            if key in {"plan", "plan_id", "plan_ids", "run", "run_id", "run_ids"}:
                if isinstance(item, str):
                    target.add(item)
                elif isinstance(item, dict) and isinstance(identifier := item.get("id"), str):
                    target.add(identifier)
                elif isinstance(item, list):
                    target.update(identifier for identifier in item if isinstance(identifier, str))
            _history_action_ids(item, plans, runs)


def _fold_read(message: ChatMessage, max_tool_bytes: int) -> ChatMessage:
    original_bytes = len(message.content.encode("utf-8"))
    if original_bytes <= max_tool_bytes:
        return message
    try:
        outcome = ToolOutcome.model_validate_json(message.content)
    except ValidationError:
        return message
    if outcome.plan is not None or outcome.run is not None:
        return message
    summary: dict[str, JsonValue] = {
        "folded": True,
        "original_bytes": original_bytes,
        "keys": list(outcome.content.root),
        "fields": {key: _preview(value) for key, value in outcome.content.root.items()},
    }
    folded = outcome.model_copy(update={"content": JsonDocument(summary)})
    return message.model_copy(update={"content": folded.model_dump_json()})


def _preview(value: JsonValue, depth: int = 0) -> JsonValue:
    if isinstance(value, str):
        return value[:240]
    if isinstance(value, list):
        return {
            "item_count": len(value),
            "preview": [_preview(item, depth + 1) for item in value[:2]]
            if depth < _PREVIEW_DEPTH
            else [],
        }
    if isinstance(value, dict):
        return {
            "keys": list(value),
            "item_count": len(value),
            "preview": {key: _preview(value[key], depth + 1) for key in list(value)[:2]}
            if depth < _PREVIEW_DEPTH
            else {},
        }
    return value
