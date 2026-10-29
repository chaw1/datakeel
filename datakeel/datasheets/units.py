# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read each number with the measurement its own context gives it."""

import re
from decimal import Decimal, InvalidOperation

from datakeel.datasheets.number_words import written_number_spans

# A reading is a value and its unit class: "percent", "count:<object>", "bytes", "score", "ratio",
# "duration", "date", "amount:<currency>", or None when the text names no unit.
Reading = tuple[Decimal, str | None]

# Count nouns retain their object identity; classifiers such as 个 or 条 alone do not name one.
_COUNT_OBJECTS = (
    ("files", r"files?\b|文件"),
    ("images", r"images?\b|图片|图像"),
    ("texts", r"texts?\b|文本"),
    ("assertions", r"assertions?\b|(?:证据)?断言"),
    ("relations", r"relations?\b|关系"),
    ("entities", r"entities\b|entity\b|实体"),
    ("records", r"records?\b|entries\b|entry\b|记录"),
    ("items", r"items?\b|条目"),
    ("events", r"events?\b|事件"),
    ("steps", r"steps?\b|步骤"),
    ("rows", r"rows?\b|行"),
    ("columns", r"columns?\b|列"),
    ("documents", r"documents?\b|文档"),
    ("observations", r"observations?\b|观测"),
    ("objects", r"objects?\b|对象"),
    ("samples", r"samples?\b|样本"),
    ("scenes", r"scenes?\b|场景"),
    ("labels", r"labels?\b|标签"),
    ("annotations", r"annotations?\b|标注"),
    ("categories", r"categories\b|category\b|类别|分类"),
    ("tables", r"tables?\b|表"),
    ("videos", r"videos?\b|视频"),
    ("people", r"people\b|persons?\b|members?\b|人|成员"),
    ("versions", r"versions?\b|版本"),
    ("predicates", r"predicates?\b|谓词"),
    ("decisions", r"decisions?\b|决定"),
    ("modalities", r"modalities\b|modality\b|模态"),
)
_COUNT_PATTERNS = tuple(
    (name, re.compile(r"(?<![a-z])(?:" + pattern + ")")) for name, pattern in _COUNT_OBJECTS
)
_CLASSIFIER = re.compile(r"\s?(?:[个张条份件项次位种篇段行列幅台处套本人]|名(?![称字])|组(?!织))")
_COUNT_MODIFIER = re.compile(r"(?:generated|labelled|labeled)\s+")

NUMBER = re.compile(
    r"(?<![A-Za-z0-9_.])[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?%?"
)
# Checked in order: "分钟" is a duration before "分" can be a score, "美元" before "元".
_FOLLOWING = (
    (
        "duration",
        re.compile(
            r"\s?(?:毫秒|秒|分钟|小时|天|周|milliseconds?\b|ms\b|seconds?\b|minutes?\b"
            r"|hours?\b|days?\b|weeks?\b)"
        ),
    ),
    ("date", re.compile(r"\s?(?:年|月|日|号)")),
    ("bytes", re.compile(r"\s?(?:字节|bytes?\b|[kmgtp]i?b\b)")),
    ("score", re.compile(r"\s?(?:分(?![钟发类布析组别成为配割享之])|points?\b|pts?\b)")),
    ("ratio", re.compile(r"\s?\(?\s?(?:比例|ratio\b)")),
    ("amount:USD", re.compile(r"\s?(?:美元|usd\b|dollars?\b)")),
    ("amount:CNY", re.compile(r"\s?(?:元(?!数据)|人民币|cny\b|rmb\b|yuan\b)")),
    ("amount:EUR", re.compile(r"\s?(?:欧元|eur\b|euros?\b)")),
)
_PRECEDING = (("amount:USD", ("us$", "$")), ("amount:CNY", ("¥",)), ("amount:EUR", ("€",)))
_PERCENT_WORDS = re.compile(r"\s(?:percent|per cent)\b")


def count_unit(text: str) -> str | None:
    """Return a canonical counted object from a declared unit or a field's words."""
    words = re.sub(r"[_.]", " ", text.casefold())
    for object_name, pattern in _COUNT_PATTERNS:
        if pattern.search(words):
            return f"count:{object_name}"
    return None


def _counted_object(text: str) -> str | None:
    unit = None
    while text:
        for object_name, pattern in _COUNT_PATTERNS:
            if match := pattern.match(text):
                unit = f"count:{object_name}"
                text = text[match.end() :].lstrip()
                break
        else:
            break
    return unit


def _count_after(text: str, end: int) -> str | None:
    tail = text[end:].lstrip(" \t'\"\u2018\u2019\u201c\u201d")
    candidates = (tail, _COUNT_MODIFIER.sub("", _CLASSIFIER.sub("", tail, count=1), count=1))
    for candidate in candidates:
        if unit := _counted_object(candidate):
            return unit
    return "count" if _CLASSIFIER.match(tail) else None


def unit_after(text: str, start: int, end: int) -> str | None:
    """Classify the unit written directly before or after one numeral."""
    before = text[:start].rstrip()
    for unit, symbols in _PRECEDING:
        if before.endswith(symbols):
            return unit
    for unit, pattern in _FOLLOWING:
        if pattern.match(text, end):
            return unit
    return _count_after(text, end)


def reading_spans(text: str) -> tuple[tuple[int, int, Reading], ...]:
    """Keep each numeral's position so a field label can support only its own number."""
    readings: list[tuple[int, int, Reading]] = []
    for start, end, value in written_number_spans(text):
        percent = text[:start].endswith("百分之") or _PERCENT_WORDS.match(text, end)
        readings.append(
            (start, end, (value, "percent" if percent else unit_after(text, start, end)))
        )
    for match in NUMBER.finditer(text):
        token = match.group()
        try:
            value = Decimal(token.replace(",", "").rstrip("%"))
        except InvalidOperation:
            continue
        unit = "percent" if token.endswith("%") else unit_after(text, match.start(), match.end())
        readings.append((match.start(), match.end(), (value, unit)))
    return tuple(sorted(readings))


def text_readings(text: str) -> tuple[Reading, ...]:
    """Return every numeral in normalized, date-free text with its contextual unit class."""
    return tuple(reading for _start, _end, reading in reading_spans(text))


def supported(reading: Reading, evidence: frozenset[Reading]) -> bool:
    """Match a value under its unit: percentages restate ratios, units must agree."""
    value, unit = reading
    if unit == "percent":
        # A percentage restates only a recorded ratio or a recorded percentage.
        return (value / 100, "ratio") in evidence or (value, "percent") in evidence
    if unit == "ratio" and (value * 100, "percent") in evidence:
        return True
    if unit is None:
        # Typed facts can support a bare number only after its own field label is bound.
        return (value, None) in evidence
    return (value, unit) in evidence or (value, None) in evidence
