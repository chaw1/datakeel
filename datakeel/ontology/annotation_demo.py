# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Disclosed offline annotation intent with answers derived from actual saved tool output."""

from datakeel.core.agent_models import ChatMessage, ModelRequest, ModelResponse, ToolCall
from datakeel.core.annotation_sampling import AnnotationQualityOverview
from datakeel.core.models import JsonDocument
from datakeel.ontology.tool_models import ToolOutcome


def respond_annotation_quality(
    request: ModelRequest, text: str, facts: JsonDocument, tools: list[ChatMessage]
) -> ModelResponse | None:
    """Discover the read tool, then report measured agreement and review counts."""
    if not any(
        word in text for word in ("标注一致", "标注质量", "annotation quality", "agreement")
    ):
        return None
    outcome = next(
        (
            ToolOutcome.model_validate_json(item.content)
            for item in tools
            if item.name == "annotation_quality"
        ),
        None,
    )
    if outcome is not None:
        if outcome.status != "SUCCEEDED":
            return ModelResponse(content="标注质量查询失败。请检查数据集和版本。")
        overview = AnnotationQualityOverview.model_validate(outcome.content.root.get("data"))
        if overview.latest is None:
            return ModelResponse(content="当前数据集版本没有标注质量报告。请先导入标注。")
        report = overview.latest
        estimate = report.result.classification.fleiss_kappa
        value = "未定义" if estimate.value is None else f"{estimate.value:.4f}"
        observed = estimate.observed_agreement
        agreement = "未定义" if observed is None else f"{observed:.2%}"
        return ModelResponse(
            content=f"这批标注有 {report.sample_count} 个样本。Fleiss κ = {value}。"
            f"原始一致率 {agreement}。疑似错标 {len(report.result.findings)} 条。"
            "疑似错标需要人工复核。完整分类、目标框、片段指标与抽检历史见工具详情。"
        )
    dataset_id = facts.root.get("dataset_id")
    if not isinstance(dataset_id, str):
        return ModelResponse(content="请先选择要评估标注质量的数据集。")
    loaded = "annotation_quality" in {tool.name for tool in request.tools}
    return ModelResponse(
        tool_calls=[
            ToolCall(
                name="annotation_quality" if loaded else "tool_search",
                arguments=JsonDocument(
                    {"dataset_id": dataset_id} if loaded else {"query": "annotation_quality"}
                ),
            )
        ],
        stop_reason="tool_calls",
    )
