# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep numerical and grouped metric phrases separate from typed knowledge questions."""

import re

from datakeel.ask.knowledge_focus import QuestionFocus, question_focus
from datakeel.ask.knowledge_names import normalize_name
from datakeel.core.metric_models import SemanticLayer

_NUMERIC = re.compile(
    r"多少|(?<!哪)几(?!张|位|些)|总额|合计|最高|最低|最多|最少|排名|前几|最大|最小|"
    r"\b(?:how\s+(?:much|many)|total|most|least|top|highest|lowest|largest|smallest)\b"
)
_TIME = re.compile(
    r"\d{4}\s*年(?:\s*\d{1,2}\s*月)?|近\s*\d+\s*天|上(?:个)?季度|"
    r"今年|去年|本月|上个月|今天|昨天|本季度|"
    r"\b(?:last|this|previous)\s+(?:month|quarter|year|week)|\b\d{4}\b"
)
_FILLER = re.compile(
    r"请问|请|看看|查看|查询|看|统计|展示|的|是|呢|呀|啊|"
    r"\b(?:please|show|me|the|a|an|in|during|at|is|are)\b|[\s?\uff1f。.!\uff01,\uff0c:\uff1a;\uff1b'\"“”]+"
)
_GROUP = re.compile(
    r"按[^?\uff1f。!\uff01,\uff0c]+|每[^?\uff1f。!\uff01,\uff0c]+|各[^?\uff1f。!\uff01,\uff0c]+|"
    r"\b(?:by|per|for)\s+[^?\uff1f。!\uff01,\uff0c]+"
)


def numeric_route(text_without_names: str, focus: QuestionFocus) -> bool:
    """Prioritize quantities except explicit requests for tables or metric lists."""
    hits = tuple(_NUMERIC.finditer(text_without_names))
    if focus.kind == "person" and focus.text not in {"owner", "负责人", "责任人", "所有者"}:
        hits = tuple(hit for hit in hits if hit.group() not in {"总额", "total"})
    return bool(hits) and focus.kind not in {"table", "metric"}


def pure_metric_phrase(question: str, layer: SemanticLayer) -> bool:
    """Strip registered metric/time/dimension terms and bounded grouping/filter clauses."""
    text = normalize_name(question)
    names = {
        normalize_name(value)
        for metric in layer.metrics
        for value in (metric.name, metric.id, *metric.synonyms)
    }
    metric_ids = {metric.id for metric in layer.metrics}
    measure_columns = {metric.measure.column for metric in layer.metrics}
    names.update(
        normalize_name(value)
        for term in layer.terms
        if (term.means.kind == "metric" and term.means.id in metric_ids)
        or (term.means.kind == "column" and term.means.id in measure_columns)
        for value in (term.term, *term.synonyms)
    )
    found = False
    for name in sorted(names, key=len, reverse=True):
        if name and name in text:
            found = True
            text = text.replace(name, " ")
    if not found:
        return False
    text = _TIME.sub(" ", text)
    if re.search(r"谁|哪|什么|\b(?:who|whose|which|what|where)\b", text):
        return False
    # Nominal filters before a metric are not requests for the relation they contain.
    text = re.sub(r"^[^谁哪什么?\uff1f]*的\s*$", "", text)
    text = _GROUP.sub("", text)
    if question_focus(text).kind != "unknown":
        return False
    for dimension in layer.dimensions:
        for value in dimension.values:
            text = text.replace(normalize_name(value), " ")
    return not _FILLER.sub("", text)


def grouped_request(text: str, focus: QuestionFocus) -> bool:
    """Keep explicitly displayed values grouped by nominal knowledge-word dimensions."""
    return focus.kind == "unknown" and bool(re.search(r"\bshow\b.*\b(?:for|by|per)\b", text))
