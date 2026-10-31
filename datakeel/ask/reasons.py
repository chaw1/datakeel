# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Coded refusal and clarification reasons, with the stored Chinese wording kept unchanged."""

from collections.abc import Iterable
from typing import Literal

from datakeel.core.ask_models import AskReason, AskReasonCode, MetricResolution
from datakeel.core.metric_models import MetricCard

_FIXED: dict[AskReasonCode, str] = {
    "ambiguous_metric": "问题对应多个指标。请选择需要的指标口径。",
    "unresolved_metric": "指标引用的目录对象尚未解析。无法执行问数。",
    "generic_metric": "问题只提到泛称, 对应多个可能的指标。请选择需要的指标口径。",
    "no_metric": "无法用已登记指标回答。以下是最接近的指标。",
    "selected_metric_missing": "选定指标不存在。请选择已登记指标。",
    "selected_metric_unresolved": "选定指标或问题条件尚未解析。无法执行问数。",
    "share_needs_grouping": "结果行占比需要明确分组维度或时间粒度。",
    "comparison_period_mismatch": "指定的对比周期与当前完整时间区间不一致。请明确月份或季度。",
    "year_over_year_needs_range": "请明确同比的时间范围。",
    "previous_period_needs_range": "请明确环比的时间范围。",
    "same_period_needs_range": "请明确同期对应的有界时间区间。",
    "followup_metric_unavailable": "上一轮指标在当前登记口径下不可用。",
    "followup_dimensions_unclear": "新指标无法明确沿用上一轮维度,请明确筛选和分组。",
    "followup_comparison_unclear": ("请明确需要的对比方式和时间分组,不支持否定或相互冲突的修改。"),
    "followup_change_unclear": "无法确定追问的修改内容,请明确指标、时间、维度取值或分组。",
}


def _quoted(items: Iterable[str]) -> str:
    return "「" + "」「".join(items) + "」"


def chinese_message(reason: AskReason) -> str:
    """Word a reason exactly as answers stored it before reasons had codes."""
    fixed = _FIXED.get(reason.code)
    if fixed is not None:
        return fixed
    notes, fragments = reason.notes, reason.fragments
    worded = {
        "time_unparsed": lambda: "无法可靠解析时间条件: " + "; ".join(notes),
        "followup_time_unparsed": lambda: "追问的时间条件不可用: " + "; ".join(notes),
        "time_not_understood": lambda: "无法可靠解析时间条件: 未理解" + _quoted(fragments),
        "unsupported_calculation": lambda: "登记指标不支持所问的计算: " + _quoted(fragments),
        "unclear_condition": lambda: (
            "请明确维度条件: " + "; ".join([*notes, *(f"未理解「{item}」" for item in fragments)])
        ),
        "execution_failed": lambda: f"已登记指标暂时无法执行 ({', '.join(notes)})。",
    }
    return worded[reason.code]()


def reason_fields(
    code: AskReasonCode, *, fragments: Iterable[str] = (), notes: Iterable[str] = ()
) -> dict[str, object]:
    """Return the `message` and `reason` fields for one coded reason."""
    reason = AskReason(code=code, fragments=tuple(fragments), notes=tuple(notes))
    return {"message": chinese_message(reason), "reason": reason}


def refusal(
    status: Literal["unanswerable", "clarification"],
    candidates: tuple[MetricCard, ...],
    code: AskReasonCode,
    *,
    fragments: Iterable[str] = (),
    notes: Iterable[str] = (),
) -> MetricResolution:
    """Refuse or ask back with a coded reason and its stored Chinese wording."""
    return MetricResolution.model_validate(
        {
            "status": status,
            "candidates": candidates,
            **reason_fields(code, fragments=fragments, notes=notes),
        }
    )
