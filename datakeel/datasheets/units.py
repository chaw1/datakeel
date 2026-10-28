# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read each number with the measurement its own context gives it."""

import re
from decimal import Decimal, InvalidOperation

from datakeel.datasheets.number_words import written_number_spans

# A reading is a value and its unit class: "percent", "count", "bytes", "score", "ratio",
# "duration", "date", "amount:<currency>", or None when the text names no unit.
Reading = tuple[Decimal, str | None]

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
    ("count", re.compile(r"\s?(?:[个张条份件项次位种篇段行列幅台处套本人]|名(?![称字])|组(?!织))")),
    (
        "count",
        re.compile(
            r"\s(?:files?|images?|texts?|items?|records?|entries|entry|assertions?|relations?"
            r"|entities|entity|events?|steps?|rows?|columns?|documents?|observations?|objects?"
            r"|samples?|scenes?|labels?|annotations?|categories|category|tables?|videos?"
            r"|people|persons?|members?|versions?|predicates?|decisions?|modalities)\b"
        ),
    ),
)
_PRECEDING = (("amount:USD", ("us$", "$")), ("amount:CNY", ("¥",)), ("amount:EUR", ("€",)))
_PERCENT_WORDS = re.compile(r"\s(?:percent|per cent)\b")


def unit_after(text: str, start: int, end: int) -> str | None:
    """Classify the unit written directly before or after one numeral."""
    before = text[:start].rstrip()
    for unit, symbols in _PRECEDING:
        if before.endswith(symbols):
            return unit
    for unit, pattern in _FOLLOWING:
        if pattern.match(text, end):
            return unit
    return None


def text_readings(text: str) -> tuple[Reading, ...]:
    """Return every numeral in normalized, date-free text with its contextual unit class."""
    readings: list[Reading] = []
    for start, end, value in written_number_spans(text):
        percent = text[:start].endswith("百分之") or _PERCENT_WORDS.match(text, end)
        readings.append((value, "percent" if percent else unit_after(text, start, end)))
    for match in NUMBER.finditer(text):
        token = match.group()
        try:
            value = Decimal(token.replace(",", "").rstrip("%"))
        except InvalidOperation:
            continue
        unit = "percent" if token.endswith("%") else unit_after(text, match.start(), match.end())
        readings.append((value, unit))
    return tuple(readings)


def supported(reading: Reading, evidence: frozenset[Reading]) -> bool:
    """Match a value under its unit: percentages restate ratios, units must agree."""
    value, unit = reading
    if unit == "percent":
        # A percentage restates only a recorded ratio or a recorded percentage.
        return (value / 100, "ratio") in evidence or (value, "percent") in evidence
    if unit in (None, "ratio") and (value * 100, "percent") in evidence:
        return True
    if unit is None:
        return any(item == value for item, _unit in evidence)
    return (value, unit) in evidence or (value, None) in evidence
