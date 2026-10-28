# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Which reads the Agent discovers on demand, and how discovery results re-enter history."""

import json

from pydantic import JsonValue, ValidationError

from datakeel.core.agent_models import ChatMessage, ToolDefinition
from datakeel.core.models import JsonDocument
from datakeel.ontology.tool_models import ToolOutcome

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
    }
)


def compact_tool_search(message: ChatMessage, loaded_tools: list[ToolDefinition]) -> ChatMessage:
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
        **outcome.content.root,
        "tools": [
            {key: value for key, value in item.items() if key != "parameters"}
            if isinstance(item, dict) and json.dumps(item, sort_keys=True) in loaded
            else item
            for item in definitions
        ],
    }
    outcome = outcome.model_copy(update={"content": JsonDocument(content)})
    return message.model_copy(update={"content": outcome.model_dump_json()})
