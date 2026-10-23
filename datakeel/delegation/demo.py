# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Demonstrate actual serial specialist execution using deterministic local responses."""

from datakeel.core.agent_models import ChatMessage, ModelRequest, ModelResponse, ToolCall
from datakeel.core.models import JsonDocument


def respond_delegation(
    request: ModelRequest, text: str, tools: list[ChatMessage]
) -> ModelResponse | None:
    """Use a small disclosed vocabulary and route child reads through the real tool layer."""
    if request.agent_name != "main":
        return (
            ModelResponse(content="目录分析完成。已检查当前数据集。")
            if tools
            else _call("list_datasets", {})
        )
    if not any(word in text for word in ("委派", "delegate")):
        return None
    if any(message.name == "delegate_agent" for message in tools):
        return ModelResponse(content="子 Agent 已完成目录分析。结论与调用记录见嵌套步骤。")
    if "delegate_agent" not in {tool.name for tool in request.tools}:
        return _call("tool_search", {"query": "delegate_agent"})
    return _call(
        "delegate_agent", {"agent": "catalog-analyst", "task": "Inspect the current datasets."}
    )


def _call(name: str, arguments: dict[str, str]) -> ModelResponse:
    return ModelResponse(
        tool_calls=[ToolCall(name=name, arguments=JsonDocument.model_validate(arguments))]
    )
