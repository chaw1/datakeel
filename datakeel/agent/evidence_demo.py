# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Disclosed offline evidence intents backed by real reads and exact returned selections."""

from collections.abc import Mapping

from datakeel.core.agent_models import ChatMessage, ModelRequest, ModelResponse, ToolCall
from datakeel.core.models import JsonDocument
from datakeel.evidence.query_models import EvidenceExplanation, EvidenceQuery, EvidenceQueryResult
from datakeel.ontology.models import AssertionFilter, ObjectSet, PropertyFilter
from datakeel.ontology.tool_models import ToolOutcome


def _call(name: str, arguments: Mapping[str, object]) -> ModelResponse:
    return ModelResponse(
        tool_calls=[ToolCall(name=name, arguments=JsonDocument.model_validate(arguments))],
        stop_reason="tool_calls",
    )


def _result(messages: list[ChatMessage], name: str) -> ToolOutcome | None:
    return next(
        (
            result
            for message in reversed(messages)
            if message.role == "tool"
            and message.name == name
            and (result := ToolOutcome.model_validate_json(message.content)).status == "SUCCEEDED"
        ),
        None,
    )


def _action(text: str) -> str | None:
    for words, name in (
        (("删除", "delete"), "delete_files"),
        (("取消隔离", "unquarantine"), "unquarantine_files"),
        (("隔离", "quarantine"), "quarantine_files"),
        (
            ("生成版本", "新版本", "create a version", "new version"),
            "create_version_from_selection",
        ),
    ):
        if any(word in text for word in words):
            return name
    return None


def _query(text: str, facts: JsonDocument) -> ModelResponse:
    dataset = facts.root.get("dataset_id")
    filters = [
        AssertionFilter(predicate="mentions", concept="person", value="present"),
        AssertionFilter(
            predicate="annotated_as", concept="person", value="present", operator="not_exists"
        ),
    ]
    if any(word in text for word in ("未知", "unknown", "无标注", "missing annotation")):
        filters.append(AssertionFilter(predicate="label_gap", concept="person", value="unknown"))
    query = EvidenceQuery(
        dataset_id=dataset if isinstance(dataset, str) else None,
        split="val",
        assertion_filters=filters,
        has_near_duplicate_in="train"
        if any(word in text for word in ("近重复", "near duplicate", "train", "训练集"))
        else None,
        page_size=2,
    )
    return _call("query_evidence", query.model_dump(mode="json"))


def _selection(result: EvidenceQueryResult) -> ObjectSet | None:
    datasets = {item.dataset_id for item in result.items}
    versions = {item.source_version for item in result.items}
    if len(datasets) != 1 or len(versions) != 1:
        return None
    return ObjectSet(
        dataset_id=next(iter(datasets)),
        version_ids=sorted(versions),
        filters=[
            PropertyFilter(
                field="id", operator="in", value=[item.asset_ref.asset_id for item in result.items]
            )
        ],
    )


def _mutate(
    request: ModelRequest, tools: list[ChatMessage], result: EvidenceQueryResult, action: str
) -> ModelResponse:
    outcome = _result(tools, action)
    if outcome is not None:
        return ModelResponse(
            content="已对本页证据样本完成受控操作。执行回执已保存。"
            if outcome.run is not None and outcome.run.status == "SUCCEEDED"
            else "计划已准备。执行状态请查看计划卡。"
        )
    selection = _selection(result)
    if selection is None:
        return ModelResponse(content="请先选择一个数据集和来源版本。然后可对本页样本执行动作。")
    if action not in {tool.name for tool in request.tools}:
        return _call("tool_search", {"query": action})
    return _call(action, {"selection": selection.model_dump(mode="json")})


def _answer(
    request: ModelRequest, text: str, tools: list[ChatMessage], result: EvidenceQueryResult
) -> ModelResponse:
    if not result.items:
        return ModelResponse(content="当前条件未返回证据样本。不能据此断言该概念不存在。")
    if action := _action(text):
        return _mutate(request, tools, result, action)
    if any(word in text for word in ("解释", "explain")):
        explained = _result(tools, "explain_sample")
        if explained is not None:
            return ModelResponse(
                content=EvidenceExplanation.model_validate(explained.content.root.get("data")).text
            )
        sample = result.items[0]
        return _call(
            "explain_sample",
            {"asset_id": sample.asset_ref.asset_id, "version_id": sample.source_version},
        )
    return ModelResponse(
        content=f"找到 {result.total} 个匹配样本。本页展示 {len(result.items)} 个。"
        "证据中的 unknown 表示未知。不能当作不存在。完整结果可在证据页分页查看。"
    )


def respond_evidence(
    request: ModelRequest, text: str, facts: JsonDocument, tools: list[ChatMessage]
) -> ModelResponse | None:
    """Query person gaps, explain actual states, and act on displayed identities.

    The offline demo shows up to two samples per response to bound retained tool
    context. Full query totals and pagination remain available in the evidence view.
    """
    previous = _result(request.messages, "query_evidence")
    explain = any(word in text for word in ("解释", "explain"))
    explicit = any(word in text for word in ("证据", "标注", "caption", "pedestrian", "行人"))
    if not explicit and not (previous and (_action(text) or explain)):
        return None
    current = _result(tools, "query_evidence")
    if current is None and (explicit or previous is None):
        return _query(text, facts)
    selected = current or previous
    if selected is None:
        return None
    result = EvidenceQueryResult.model_validate(selected.content.root.get("data"))
    return _answer(request, text, tools, result)
