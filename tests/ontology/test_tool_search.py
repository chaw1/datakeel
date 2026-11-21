# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bilingual discovery ranks useful schemas while bounding broad-query prompt growth."""

import pytest
from pydantic import ValidationError

from datakeel.agent.tools import deferred_tools
from datakeel.core.agent_models import ToolDefinition
from datakeel.core.models import JsonDocument
from datakeel.ontology.tool_search import (
    DEFAULT_TOOL_SEARCH_LIMIT,
    ToolSearchParams,
    search_tools,
)


def _tool(name: str, description: str = "") -> ToolDefinition:
    return ToolDefinition(name=name, description=description, parameters=JsonDocument({}))


def _names(result: JsonDocument) -> list[str]:
    values = result.root["tools"]
    assert isinstance(values, list)
    return [ToolDefinition.model_validate(value).name for value in values]


@pytest.mark.parametrize("query", ["QUARANTINE_FILES", "quarantine files", "quarantine-files"])
def test_search_when_exact_name_normalized_returns_only_that_schema(query: str) -> None:
    """An exact name wins over inverse actions and descriptions with the same terms."""
    tools = [_tool("unquarantine_files", "quarantine files"), _tool("quarantine_files")]
    result = search_tools(tools, ToolSearchParams(query=query))
    assert result.root == {
        "tools": [tools[1].model_dump(mode="json")],
        "total_matches": 1,
        "truncated": False,
    }


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("quarantine file", "quarantine_files"),
        ("label set", "label_set_diff"),
        ("返工 率", "rework_rate"),
        ("数据集 质量", "get_training_quality"),
    ],
)
def test_search_when_multilingual_words_separated_recalls_registered_tools(
    query: str, expected: str
) -> None:
    """English identifier stems and Chinese character n-grams reach real catalog schemas."""
    result = search_tools(deferred_tools(), ToolSearchParams(query=query))
    assert expected in _names(result)
    assert len(_names(result)) <= DEFAULT_TOOL_SEARCH_LIMIT


def test_search_when_ranked_prioritizes_name_and_keeps_ties_order_independent() -> None:
    """Name hits outrank description hits and tied tools sort by stable identifier."""
    tools = [_tool("z_read", "quarantine file"), _tool("a_read", "quarantine file")]
    tools.append(_tool("quarantine_files"))
    params = ToolSearchParams(query="quarantine file")
    result = search_tools(tools, params)
    assert _names(result) == ["quarantine_files", "a_read", "z_read"]
    assert search_tools(list(reversed(tools)), params) == result


@pytest.mark.parametrize("limit", [DEFAULT_TOOL_SEARCH_LIMIT, 3, 20])
def test_search_when_broad_caps_full_schemas_and_reports_all_matches(limit: int) -> None:
    """Bound JSON schemas while reporting matches beyond the returned window."""
    tools = [_tool(f"read_{index:02}", "dataset") for index in range(30)]
    result = search_tools(tools, ToolSearchParams(query="datasets", limit=limit))
    assert _names(result) == [tool.name for tool in tools[:limit]]
    assert result.root["total_matches"] == 30
    assert result.root["truncated"] is True
    broad = search_tools(deferred_tools(), ToolSearchParams(query="dataset"))
    assert len(_names(broad)) == DEFAULT_TOOL_SEARCH_LIMIT
    assert broad.root["truncated"] is True


@pytest.mark.parametrize("limit", [0, 21])
def test_search_when_limit_outside_bounds_rejects_request(limit: int) -> None:
    """The advertised discovery limit cannot disable the schema cap."""
    with pytest.raises(ValidationError):
        ToolSearchParams(query="dataset", limit=limit)


@pytest.mark.parametrize(("query", "expected"), [("*", ["read"]), ("!", []), ("   ", [])])
def test_search_when_query_has_no_tokens_uses_nonempty_substring_fallback(
    query: str, expected: list[str]
) -> None:
    """Symbols retain legacy substring lookup without turning whitespace into all schemas."""
    result = search_tools([_tool("read", "Supports *")], ToolSearchParams(query=query))
    assert _names(result) == expected
    assert result.root["total_matches"] == len(expected)
    assert result.root["truncated"] is False
    assert _names(search_tools([], ToolSearchParams(query="dataset"))) == []
