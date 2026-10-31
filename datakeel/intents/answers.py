# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run one read-only function directly and phrase its result."""

import logging
import re

from pydantic import JsonValue

from datakeel.core.intent_models import ReadAnswer
from datakeel.core.models import JsonDocument
from datakeel.intents.object_answers import objects_text
from datakeel.intents.plain_words import ENUM_LABELS, enum_label, key_label
from datakeel.intents.wording import action_title
from datakeel.ontology.tool_models import ToolCallContext
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.database import Database

logger = logging.getLogger(__name__)
SUMMARY_LIMIT = 600
# Keys whose values are names people gave, never a fixed choice to translate.
NAMED_KEYS = frozenset({"name", "label", "actor", "filename", "title", "holder", "description"})
LIST_LIMIT = 10
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


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


def _holding(data: JsonValue, language: str) -> str | None:
    people = _people(data)
    if not people:
        return None
    rows = sorted(people, key=lambda item: (-_number(item, "assigned"), str(item.get("actor"))))
    parts = [
        f"{item.get('actor')} {int(_number(item, 'assigned'))}/{int(_number(item, 'completed'))}"
        for item in rows[:10]
    ]
    if language == "zh":
        return "每人分到/已完成的任务数: " + ", ".join(parts) + "。"
    return "Tasks assigned/completed per person: " + ", ".join(parts) + "."


def _unanswered(data: JsonValue, language: str) -> str | None:
    """A question no registered metric answers is said so, not dumped as evidence."""
    if not isinstance(data, dict) or data.get("status") != "unanswerable":
        return None
    if language == "zh":
        return (
            "已登记的指标回答不了这个问题。可以直接问具体的数据, 比如数据集列表、找文件或治理报告。"
        )
    return (
        "No registered metric answers this question. Ask for the data directly instead, "
        "such as the list of datasets, a file search or the governance report."
    )


def answer_text(function: str, data: JsonValue, language: str) -> str:
    """Prefer a sentence for well-known reads, otherwise a compact data summary."""
    phrases = {
        "rework_rate": _workload,
        "annotator_workload": _holding,
        "ask_data": _unanswered,
        "production_objects": objects_text,
    }
    phrase = phrases.get(function)
    sentence = phrase(data, language) if phrase else None
    if sentence:
        return sentence
    summary = readable(data, language=language)
    if len(summary) > SUMMARY_LIMIT:
        summary = summary[:SUMMARY_LIMIT] + "…"
    return f"{action_title(function, language)}: {summary}"


def _hidden(key: str, value: JsonValue) -> bool:
    """Identities mean nothing to a person reading the answer; the data keeps them."""
    if key == "id" or key.endswith(("_id", "_ids")):
        return True
    return isinstance(value, str) and UUID.fullmatch(value) is not None


def _shown(key: str, value: JsonValue, language: str) -> str:
    """A fixed choice in words (pending reads 未开始); names people gave stay as they are."""
    if isinstance(value, str) and key not in NAMED_KEYS and value in ENUM_LABELS:
        return enum_label(value, language)
    return str(value)


def _pair(item: dict[str, JsonValue], language: str) -> str | None:
    """{"state": "pending", "count": 1} reads as "未开始 1"."""
    shown = [(key, value) for key, value in item.items() if not _hidden(key, value)]
    if len(shown) == 2 and all(not isinstance(value, dict | list) for _, value in shown):  # noqa: PLR2004
        return " ".join(_shown(key, value, language) for key, value in shown)
    return None


def readable(data: JsonValue, depth: int = 0, *, language: str = "en", key: str = "") -> str:
    """A compact plain summary: names and numbers, without ids, raw keys or JSON punctuation."""
    if isinstance(data, dict):
        parts = [
            f"{key_label(name, language)}: "
            + readable(value, depth + 1, language=language, key=name)
            for name, value in data.items()
            if not _hidden(name, value) and value not in (None, [], {})
        ]
        joined = "; ".join(parts) if depth == 0 else ", ".join(parts)
        return joined if depth == 0 else f"({joined})"
    if isinstance(data, list):
        items = [
            _pair(item, language) if isinstance(item, dict) else None for item in data[:LIST_LIMIT]
        ]
        shown = [
            pair if pair is not None else readable(item, depth + 1, language=language, key=key)
            for pair, item in zip(items, data[:LIST_LIMIT], strict=True)
        ]
        more = f" … +{len(data) - LIST_LIMIT}" if len(data) > LIST_LIMIT else ""
        return ", ".join(shown) + more
    if isinstance(data, float):
        return f"{data:.4g}"
    return "-" if data is None else _shown(key, data, language)


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
        # The raw error names internals; it goes to the log, the person gets plain words.
        logger.warning("Read %s failed: %s", function, outcome.error)
        title = action_title(function, language)
        if language == "zh":
            return None, f"{title}这个查询没能完成, 什么都没改。请换个说法或稍后再试。"
        return None, f"The read ({title}) could not finish; nothing changed. Please try again."
    data = outcome.content.root.get("data")
    return ReadAnswer(function=function, arguments=arguments, data=data), answer_text(
        function, data, language
    )
