# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run one read-only function directly and phrase its result."""

import json

from pydantic import JsonValue

from datakeel.core.intent_models import ReadAnswer
from datakeel.core.models import JsonDocument
from datakeel.intents.wording import action_title
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.database import Database

SUMMARY_LIMIT = 600


def _number(item: dict[str, JsonValue], key: str) -> float:
    value = item.get(key)
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


def _people(data: JsonValue) -> list[dict[str, JsonValue]]:
    rows = data.get("annotators") if isinstance(data, dict) else None
    return [item for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []


def _workload(data: JsonValue, language: str) -> str | None:
    if not isinstance(data, dict) or not isinstance(data.get("annotators"), list):
        return None
    reviewed = [item for item in _people(data) if _number(item, "review_count") > 0]
    if not reviewed:
        return "还没有审核记录, 算不出返工率。" if language == "zh" else "No reviews yet."
    top = max(reviewed, key=lambda item: (_number(item, "rework_rate"), str(item.get("actor"))))
    rate, actor = _number(top, "rework_rate"), top.get("actor")
    count, total = int(_number(top, "rework_count")), int(_number(top, "review_count"))
    if language == "zh":
        return (
            f"返工率最高的是 {actor}: {rate:.0%} ({total} 次审核里返工 {count} 次)。"
            "该函数按项目全部审核记录统计, 不按周筛选。"
        )
    return (
        f"{actor} has the highest rework rate: {rate:.0%} ({count} of {total} reviews). "
        "The function counts every review in the project; it does not filter by week."
    )


def answer_text(function: str, data: JsonValue, language: str) -> str:
    """Prefer a sentence for well-known reads, otherwise a compact data summary."""
    if function in {"rework_rate", "annotator_workload"}:
        sentence = _workload(data, language)
        if sentence:
            return sentence
    summary = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if len(summary) > SUMMARY_LIMIT:
        summary = summary[:SUMMARY_LIMIT] + "…"
    return f"{action_title(function, language)}: {summary}"


def run_read(
    db: Database,
    function: str,
    arguments: dict[str, JsonValue],
    context: ToolCallContext,
    language: str,
) -> tuple[ReadAnswer | None, str]:
    """Invoke through the audited tool boundary with the person's own access."""
    outcome = invoke_tool(db, function, JsonDocument(arguments), context)
    if outcome.status != "SUCCEEDED":
        prefix = "查询失败: " if language == "zh" else "The read failed: "
        return None, prefix + (outcome.error or "")
    data = outcome.content.root.get("data")
    return ReadAnswer(function=function, arguments=arguments, data=data), answer_text(
        function, data, language
    )
