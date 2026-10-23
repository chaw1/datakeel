# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic offline demo intents backed by actual controlled platform tools."""

import re
from collections.abc import Mapping

from datakeel.agent.evidence_demo import respond_evidence
from datakeel.core.agent_models import ChatMessage, ModelRequest, ModelResponse, ToolCall
from datakeel.core.envelopes import unwrap
from datakeel.core.harness_models import TokenUsage
from datakeel.core.models import JsonDocument
from datakeel.delegation.demo import respond_delegation
from datakeel.ontology.tool_models import ToolOutcome


class DemoProvider:
    """Translate a small disclosed demo vocabulary into real tool protocol exchanges."""

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Use the complete session transcript to resolve current-turn progress."""
        request = request.model_copy(update={"messages": [unwrap(m) for m in request.messages]})
        users = [
            index
            for index, message in enumerate(request.messages)
            if message.role == "user" and not message.name
        ]
        index = users[-1]
        text = request.messages[index].content.casefold()
        facts = JsonDocument.model_validate_json(request.messages[-1].content)
        tools = [message for message in request.messages[index + 1 :] if message.role == "tool"]
        response = self._respond(request, text, facts, tools)
        return response.model_copy(
            update={
                "usage": TokenUsage(
                    input_tokens=max(1, sum(segment.tokens for segment in request.segments) // 4),
                    output_tokens=max(1, len(response.model_dump_json().encode()) // 4),
                )
            }
        )

    def _respond(
        self, request: ModelRequest, text: str, facts: JsonDocument, tools: list[ChatMessage]
    ) -> ModelResponse:
        evidence = respond_delegation(request, text, tools) or (
            ModelResponse(content="工具调用失败。请检查工具结果后重试。")
            if tools and ToolOutcome.model_validate_json(tools[-1].content).status == "FAILED"
            else respond_evidence(request, text, facts, tools)
        )
        if evidence is not None:
            return evidence
        dataset_id = _dataset(facts)
        action = _intent(text)
        completed = {message.name for message in tools}
        if dataset_id is None or action == "list_datasets":
            return (
                _call("list_datasets", {})
                if not tools
                else ModelResponse(content="已列出当前数据集。")
            )
        if action.startswith("get_"):
            key = "asset_id" if action == "get_lineage" else "dataset_id"
            return (
                _call(action, {key: dataset_id})
                if not tools
                else ModelResponse(content="查询完成。结果见工具详情。")
            )
        selection = _selection(request, dataset_id, text)
        if "search_files" not in completed:
            arguments = {
                "dataset_id": dataset_id,
                "modality": "text",
                "quality_max": selection.root.get("quality_max", 60),
            }
            return _call("search_files", arguments)
        if action == "search_files":
            return ModelResponse(content="已找到符合条件的文件。筛选结果见工具详情。")
        return self._action(request, text, selection, completed, action)

    def _action(
        self,
        request: ModelRequest,
        text: str,
        selection: JsonDocument,
        completed: set[str | None],
        action: str,
    ) -> ModelResponse:
        if action in completed:
            if action == "quarantine_files" and ("版本" in text or "version" in text):
                action = "create_version_from_selection"
            elif action == "run_pipeline":
                return ModelResponse(content="任务已排队。worker 完成后可查看执行回执。")
            else:
                return ModelResponse(content="已完成受控操作。执行回执已保存。可在血缘图查看。")
        if action in completed:
            return ModelResponse(content="已隔离所选样本并生成新版本。执行回执已保存。")
        if action not in {tool.name for tool in request.tools}:
            return _call("tool_search", {"query": action})
        if action in {"export_dataset", "run_pipeline"}:
            return _call(action, {"dataset_id": selection.root["dataset_id"]})
        return _call(action, {"selection": selection.root})


def _dataset(facts: JsonDocument) -> str | None:
    selected = facts.root.get("dataset_id")
    if isinstance(selected, str):
        return selected
    datasets = facts.root.get("datasets")
    if isinstance(datasets, list) and datasets and isinstance(datasets[0], dict):
        value = datasets[0].get("id")
        return value if isinstance(value, str) else None
    return None


def _intent(text: str) -> str:
    intents = [
        (("删除", "delete"), "delete_files"),
        (("取消隔离", "unquarantine"), "unquarantine_files"),
        (("隔离", "quarantine"), "quarantine_files"),
        (("导出", "export"), "export_dataset"),
        (("版本", "version"), "create_version_from_selection"),
        (("处理", "pipeline"), "run_pipeline"),
        (("报告", "report"), "get_report"),
        (("血缘", "lineage"), "get_lineage"),
        (("低于", "搜索", "search", "files", "文件"), "search_files"),
        (("质量", "quality"), "get_quality"),
    ]
    return next(
        (name for words, name in intents if any(word in text for word in words)), "list_datasets"
    )


def _selection(request: ModelRequest, dataset_id: str, text: str) -> JsonDocument:
    threshold = 60.0
    for message in request.messages:
        for call in message.tool_calls:
            previous = call.arguments.root.get("quality_max")
            if call.name == "search_files" and isinstance(previous, (int, float)):
                threshold = previous
    match = re.search(r"(?:低于|below|under|小于)\s*(\d+(?:\.\d+)?)", text)
    if match:
        threshold = float(match.group(1))
    return JsonDocument(
        {
            "dataset_id": dataset_id,
            "quality_max": threshold,
            "filters": [{"field": "modality", "value": "text"}],
        }
    )


def _call(name: str, arguments: Mapping[str, object]) -> ModelResponse:
    return ModelResponse(
        tool_calls=[ToolCall(name=name, arguments=JsonDocument.model_validate(arguments))],
        stop_reason="tool_calls",
    )
