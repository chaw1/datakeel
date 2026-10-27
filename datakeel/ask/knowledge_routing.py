# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep numerical and grouped metric phrases separate from typed knowledge questions."""

import re
from datetime import date

from datakeel.ask import dimension_cues
from datakeel.ask import knowledge_vocabulary as vocabulary
from datakeel.ask.dimensions import dimension_mentions
from datakeel.ask.knowledge_focus import QuestionFocus, has_relation, question_focus
from datakeel.ask.knowledge_names import normalize_name
from datakeel.ask.knowledge_scope import question_scope
from datakeel.ask.matching import metric_matches
from datakeel.ask.time import time_spans
from datakeel.core.metric_models import SemanticLayer

_SPAN_REFERENCE = date(2000, 1, 1)
_NUMERIC = re.compile(
    r"多少|(?<!哪)几(?!张|位|些)|总额|合计|最高|最低|最多|最少|排名|前几|最大|最小|"
    r"\b(?:how\s+(?:much|many)|total|most|least|top|highest|lowest|largest|smallest)\b"
)
_QUANTITY = re.compile(r"多少|(?<![哪前])几|\b(?:how\s+(?:much|many)|number\s+of)\b")
_TIME = re.compile(
    r"(?:\d{4}\s*年(?:\s*\d{1,2}\s*月)?|近\s*\d+\s*天|上(?:个)?季度|"
    r"今年|去年|本月|上个月|上月|今天|昨天|本季度|\btoday\b|\byesterday\b|"
    r"\b(?:last|this|previous)\s+(?:month|quarter|year|week)\b|\b\d{4}\b)(?:['\u2019]s)?"
)
_FILLER = re.compile(
    r"请问|请|看看|查看|查询|看|统计|展示|给我|把|的|是|呢|呀|啊|"
    r"\b(?:please|show|me|the|a|an|in|during|at|is|are)\b|[\s?\uff1f。.!\uff01,\uff0c:\uff1a;\uff1b'\"“”]+"
)
_GROUP = re.compile(
    r"(?:按|分(?!管)|每|各)[^?\uff1f。!\uff01,\uff0c]+|"
    r"\b(?:group(?:ed)?\s+by|(?:break\s+)?down\s+by|by|per|for)\s+[^?\uff1f。!\uff01,\uff0c]+|"
    r"\beach\s+[^?\uff1f。!\uff01,\uff0c]+?['\u2019]s\s+"
)
_PERSON_ASK = re.compile(
    r"谁|哪位|哪(?:个|些|支)?(?:团队|部门|组|人)|"
    r"\b(?:who|whose)\b|\b(?:which|what)\s+(?:(?:source|downstream|responsible)\s+)?"
    r"(?:teams?|people|persons?|owners?)\b"
)
_OWNER_HEAD = re.compile(r"负责人|责任人|所有者|\bowners?\s+of\b|\bowner\s*[?!.]*\s*$")
_BUSINESS_RANKING = re.compile(
    r"\bwhich\s+owners?\s+(?:has|have|manages?)\s+(?:the\s+)?"
    r"(?:most|least|highest|lowest|largest|smallest|top)\b|"
    r"\bwho\s+(?:manages?|operates?|runs?)\s+(?:the\s+)?"
    r"(?:regions?|stores?|branches|accounts?|territories|outlets?)\b[^?!.]*"
    r"\bwith\s+(?:the\s+)?(?:most|least|highest|lowest|largest|smallest|top)\b|"
    r"(?:谁|哪位)(?:负责|管理|经营)的[^?\uff1f。\uff0c,]*(?:最高|最低|最多|最少)"
)


def numeric_route(text_without_names: str, focus: QuestionFocus, *, question: str) -> bool:
    """Prioritize quantities except explicit requests for tables or metric lists."""
    if text_without_names != question and _requested_person(text_without_names):
        return False
    if _explicit_value_question(text_without_names, focus, question):
        return True
    if focus.counted and _business_count(text_without_names, focus):
        return True
    if focus.counted:
        return False
    if _QUANTITY.search(text_without_names):
        return True
    numeric_text = re.sub(vocabulary.STRUCTURAL_TOP, " ", text_without_names)
    hits = tuple(_NUMERIC.finditer(numeric_text))
    relational = has_relation(text_without_names) or re.search(
        vocabulary.CALCULATION_QUESTION, text_without_names
    )
    if focus.kind in {"person", "location"} or (focus.kind == "list" and relational):
        hits = tuple(
            hit for hit in hits if not re.fullmatch(vocabulary.SCALAR_AGGREGATE, hit.group())
        )
    return bool(hits) and focus.kind not in {"table", "metric"}


def _explicit_value_question(text: str, focus: QuestionFocus, question: str) -> bool:
    match = re.search(vocabulary.VALUE_QUESTION, text)
    if not match or re.search(vocabulary.VALUE_RELATION_END, question):
        return False
    if re.fullmatch(vocabulary.POSSESSIVE_RELATION_HEAD, text[match.end() :]):
        return False
    if focus.counted and re.search(vocabulary.VALUE_COUNT_NOUNS, match.group()):
        between = slice(focus.start + len(focus.text), match.start())
        if focus.start >= match.start() or text[between] == question[between]:
            return False
    reading = re.search(vocabulary.VALUE_READING_WORD, match.group())
    return not reading or bool(re.search(vocabulary.VALUE_READING_NOUN, text))


def _business_count(text: str, focus: QuestionFocus) -> bool:
    text = question_scope(text)
    after = text[focus.start + len(focus.text) :]
    if re.match(vocabulary.BUSINESS_HEAD_SUFFIX, after):
        return True
    if re.search(vocabulary.BUSINESS_QUANTITY, text):
        return True
    activity = re.search(vocabulary.BUSINESS_ACTIVITY, after)
    return bool(
        focus.kind == "person"
        and activity
        and re.fullmatch(vocabulary.PREDICATE_AUXILIARIES, after[: activity.start()])
    )


def pure_metric_phrase(question: str, layer: SemanticLayer) -> bool:
    """Strip registered metric/time/dimension terms and bounded grouping/filter clauses."""
    text = _masked_metrics(normalize_name(question), layer)
    if text is None or _requested_person(text):
        return False
    text, conditioned = _masked_conditions(text, layer)
    timed = conditioned or _TIME.search(text) is not None
    text = _TIME.sub(" ", text)
    text, grouped = _strip_grouping(text)
    text = re.sub(vocabulary.METRIC_WHERE_FILTER, vocabulary.SUBJECT_MARKER, text)
    if _metric_scalar_head(text, question, timed=timed or grouped) or _scalar_request(
        text, grouped=grouped
    ):
        return True
    text = text.replace(vocabulary.SUBJECT_MARKER, " ")
    if re.search(r"谁|哪|什么|\b(?:who|whose|which|what|where)\b", text):
        return False
    if not _FILLER.sub("", text):
        return True
    # Nominal filters before a metric are not requests for the relation they contain.
    text = re.sub(r"^[^谁哪什么?\uff1f]*的\s*$", "", text)
    if question_focus(text).kind != "unknown":
        return False
    for dimension in layer.dimensions:
        for value in dimension.values:
            text = text.replace(normalize_name(value), " ")
    return not _FILLER.sub("", text)


def _masked_conditions(text: str, layer: SemanticLayer) -> tuple[str, bool]:
    """Blank parsed periods and registered filter values with their attached prepositions.

    A period or a filter value both mark a value question: definitions take neither.
    """
    spans = list(time_spans(text, _SPAN_REFERENCE))
    for item in dimension_mentions(text, layer):
        if item.value is not None:
            lead = dimension_cues.FILTER_BEFORE.search(text[: item.start])
            spans.append((lead.start() if lead else item.start, item.end))
    characters = list(text)
    for start, end in spans:
        characters[start:end] = " " * (end - start)
    return "".join(characters), bool(spans)


def _masked_metrics(text: str, layer: SemanticLayer) -> str | None:
    spans: list[tuple[int, int]] = []
    for match in sorted(metric_matches(text, layer), key=lambda item: (item.start, -item.end)):
        if match.match_kind == "prefix":
            continue
        if spans and match.start < spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], match.end))
        else:
            spans.append((match.start, match.end))
    if not spans:
        return None
    for start, end in reversed(spans):
        text = text[:start] + vocabulary.SUBJECT_MARKER + text[end:]
    return text


def _requested_person(text: str) -> bool:
    ungrouped, _ = _strip_grouping(question_scope(text))
    ungrouped = re.sub(r"(?:按|每|各)\s*(?:负责人|责任人|所有者|团队|人员)", " ", ungrouped)
    focus = question_focus(ungrouped)
    return bool(
        focus.kind == "person"
        and not focus.counted
        and (_PERSON_ASK.search(ungrouped) or _OWNER_HEAD.search(ungrouped))
        and not _BUSINESS_RANKING.search(ungrouped)
    )


def grouped_request(text: str, focus: QuestionFocus) -> bool:
    """Keep explicitly displayed values grouped by nominal knowledge-word dimensions."""
    return focus.kind == "unknown" and bool(re.search(r"\bshow\b.*\b(?:for|by|per)\b", text))


def _strip_grouping(text: str) -> tuple[str, bool]:
    ungrouped = _GROUP.sub(_group_clause, text)
    if ungrouped == text:
        return text, False
    command = (
        r"^[\s,\uff0c]*(?:please\s+)?"
        r"(?:break(?:\s+down)?|group|give(?:\s+me)?|show|display|list)\s+"
    )
    return re.sub(command, "", ungrouped), True


def _group_clause(match: re.Match[str]) -> str:
    retained = re.search(vocabulary.GROUP_QUESTION_CLAUSE, match.group()) or re.fullmatch(
        vocabulary.GROUPED_SCALAR_OUTPUT, match.group()
    )
    if retained:
        return match.group()
    subject = match.group().find(vocabulary.SUBJECT_MARKER)
    return match.group()[subject:] if subject >= 0 else ""


def _metric_scalar_head(text: str, question: str, *, timed: bool) -> bool:
    if not re.fullmatch(vocabulary.METRIC_SCALAR_HEAD, text):
        return False
    return timed or bool(
        re.search(vocabulary.VALUE_QUESTION, normalize_name(question))
        or re.search(vocabulary.SCALAR_REDUCTION, text)
    )


def _scalar_request(text: str, *, grouped: bool) -> bool:
    if grouped and re.fullmatch(vocabulary.SCALAR_OUTPUT_COMMAND, text):
        return True
    quantity = re.search(vocabulary.METRIC_QUANTITY_HEAD, text)
    if quantity and not re.search(vocabulary.QUESTION_ANCHOR, text[: quantity.start()]):
        return True
    focus = question_focus(text)
    return bool(
        focus.kind in {"unknown", "list", "location"}
        and not has_relation(text)
        and re.search(vocabulary.SCALAR_COMPARISON, text)
    )
