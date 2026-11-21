# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep discovery schemas and large read history compact only at the prompt boundary."""

import json
from collections.abc import Sequence

from pydantic import JsonValue, ValidationError

from datakeel.core.agent_models import ChatMessage, ToolDefinition
from datakeel.core.models import JsonDocument
from datakeel.ontology.tool_models import ToolOutcome

_PREVIEW_DEPTH = 2

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
    return compacted


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
