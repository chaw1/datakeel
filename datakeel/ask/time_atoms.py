# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Extract calendar and relative period atoms from Chinese and English questions."""

import re
from calendar import monthrange
from collections.abc import Callable
from datetime import date, timedelta

from datakeel.ask import time_vocabulary as vocab
from datakeel.ask.models import TimeAtom

_I = re.IGNORECASE
_A = r"(?<![a-z0-9])"
_Z = r"(?![a-z0-9])"
_DAY = r"(?P<day>\d{1,2})"
_MM = r"(?P<mm>\d{1,2})"
_CALENDAR: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, _I), kind)
    for pattern, kind in (
        (rf"{vocab.MONTH}\s+{_DAY}(?:st|nd|rd|th)?,?\s+{vocab.YEAR}", "day"),
        (rf"{_A}{_DAY}(?:st|nd|rd|th)?\s+(?:of\s+)?{vocab.MONTH},?\s+{vocab.YEAR}", "day"),
        (rf"{vocab.YEAR}[-/.]{_MM}[-/.]{_DAY}(?![0-9])", "day"),
        (rf"{vocab.YEAR}\s*年\s*{vocab.CN_MONTH}\s*月\s*{_DAY}\s*[日号]", "day"),
        (rf"(?<![0-9年])(?P<mm>\d{{1,2}})\s*月\s*{_DAY}\s*[日号]", "day"),
        (rf"{vocab.MONTH}\s+{_DAY}(?:st|nd|rd|th)?(?![0-9])", "day"),
        (
            rf"(?:{vocab.YEAR}\s*年\s*)?(?<![0-9])(?P<m1>\d{{1,2}})\s*[-~\uff5e到至\u2014]\s*(?P<m2>\d{{1,2}})\s*月份?",
            "months",
        ),
        (rf"{vocab.MONTH},?\s+(?:of\s+)?{vocab.YEAR}", "month"),
        (rf"{vocab.YEAR}[-/]{_MM}(?![0-9/.-])", "month"),
        (rf"(?<![0-9/.-]){_MM}/{vocab.YEAR}", "month"),
        (rf"{vocab.YEAR}\s*年\s*{vocab.CN_MONTH}\s*月份?", "month"),
        (rf"(?<![0-9个本上下这当每近几数多前后]){vocab.CN_MONTH}\s*月份?(?!度)", "month"),
        (vocab.MONTH, "month"),
        (rf"{_A}q(?P<q>[1-4])\s*[-/' ,]?\s*(?:of\s+)?{vocab.YEAR}", "quarter"),
        (rf"{vocab.YEAR}\s*年?\s*[-/ ]?\s*q(?P<q>[1-4]){_Z}", "quarter"),
        (rf"{_A}{vocab.ORDINAL}\s+quarter\s*(?:of|in|,)?\s*{vocab.YEAR}", "quarter"),
        (rf"{vocab.YEAR}\s+{vocab.ORDINAL}\s+quarter{_Z}", "quarter"),
        (rf"{_A}quarter\s+(?P<q>[1-4])\s*(?:of|,)?\s*{vocab.YEAR}", "quarter"),
        (rf"{vocab.YEAR}\s*年\s*(?:的)?\s*(?:第\s*)?{vocab.CN_QUARTER}\s*季度?", "quarter"),
        (rf"第\s*{vocab.CN_QUARTER}\s*季度?", "quarter"),
        (rf"(?<![0-9]){vocab.CN_QUARTER}\s*季度", "quarter"),
        (rf"{_A}q(?P<q>[1-4]){_Z}", "quarter"),
        (rf"{_A}{vocab.ORDINAL}\s+quarter{_Z}", "quarter"),
        (rf"{_A}quarter\s+(?P<q>[1-4]){_Z}", "quarter"),
        (rf"{_A}(?P<h>first|second|1st|2nd)\s+half\s+(?:of\s+)?{vocab.YEAR}", "half"),
        (rf"{_A}h(?P<hn>[12])\s*[-/ ]?\s*{vocab.YEAR}", "half"),
        (rf"{vocab.YEAR}\s*[-/ ]?\s*h(?P<hn>[12]){_Z}", "half"),
        (rf"(?:{vocab.YEAR}\s*年\s*(?:的)?\s*)?(?P<ch>上|下)半年", "half"),
        (rf"{_A}(?P<h>first|second|1st|2nd)\s+half{_Z}", "half"),
        (rf"{vocab.YEAR}\s*年(?:度)?(?:全年)?", "year"),
        (rf"{_A}(?:calendar\s+)?year\s+{vocab.YEAR}", "year"),
        (vocab.YEAR, "year"),
    )
)
_RELATIVE_EN = re.compile(
    rf"{_A}(?P<rel>last|previous|prior|this|current|next|coming|past)\s+"
    rf"(?P<unit>week|month|quarter|year){_Z}",
    _I,
)
_TO_DATE = re.compile(
    rf"{_A}(?:(?P<unit>year|month|quarter|week)[- ]to[- ]date|(?P<abbr>ytd|mtd|qtd|wtd)){_Z}", _I
)
_DAY_WORD = re.compile(
    rf"{_A}(?P<word>today|yesterday|tomorrow){_Z}|(?P<cn>今天|今日|昨天|昨日|前天|明天)", _I
)
_RELATIVE_CN = re.compile(
    r"(?P<prefix>上上个?|上一个|上个|上|本|这一个|这个|这|当|今|去|前|下一个|下个|下|明)\s*"
    r"(?P<unit>月份?|季度|季|年度|年|周|星期)"
)
_TRAILING_EN = re.compile(
    rf"{_A}(?:last|past|previous|prior|trailing)\s+{vocab.COUNT}\s+"
    rf"(?P<unit>days?|weeks?|months?|quarters?|years?){_Z}",
    _I,
)
_TRAILING_CN = re.compile(
    rf"(?:近|最近|过去)\s*{vocab.CN_COUNT}\s*个?\s*(?P<unit>天|日|周|星期|月|季度|年)"
)
_CN_UNITS: dict[str, str] = {
    "月": "month",
    "月份": "month",
    "季度": "quarter",
    "季": "quarter",
    "年": "year",
    "年度": "year",
    "周": "week",
    "星期": "week",
    "天": "day",
    "日": "day",
}
_CN_OFFSETS: dict[str, int] = {
    "上上": -2,
    "上": -1,
    "本": 0,
    "这": 0,
    "当": 0,
    "今": 0,
    "去": -1,
    "前": -2,
    "下": 1,
    "明": 1,
}
_CN_VALID = {
    "上上": {"month", "quarter", "week"},
    "上": {"month", "quarter", "year", "week"},
    "本": {"month", "quarter", "year", "week"},
    "这": {"month", "quarter", "year", "week"},
    "当": {"month", "quarter"},
    "今": {"year"},
    "去": {"year"},
    "前": {"year"},
    "下": {"month", "quarter", "year", "week"},
    "明": {"year"},
}
_EN_OFFSETS: dict[str, int] = {
    "last": -1,
    "previous": -1,
    "prior": -1,
    "this": 0,
    "current": 0,
    "next": 1,
    "coming": 1,
    "past": -1,
}
_MONTHS = {"month": 1, "quarter": 3, "year": 12}
_DAY_OFFSETS: dict[str, int] = {
    "today": 0,
    "今天": 0,
    "今日": 0,
    "yesterday": -1,
    "昨天": -1,
    "昨日": -1,
    "前天": -2,
    "tomorrow": 1,
    "明天": 1,
}
_MAX_DAYS = 3650
FUTURE_ISSUE = "Future periods are not supported"


def shift_months(value: date, months: int) -> date:
    """Move a day by whole calendar months, clamping it to the target month's length."""
    year, month = divmod(value.year * 12 + value.month - 1 + months, 12)
    return date(year, month + 1, min(value.day, monthrange(year, month + 1)[1]))


def period_start(reference: date, unit: str) -> date:
    """Return the first day of the calendar week, month, quarter or year containing a day."""
    if unit == "week":
        return reference - timedelta(days=reference.weekday())
    if unit == "day":
        return reference
    months = _MONTHS[unit]
    return date(reference.year, (reference.month - 1) // months * months + 1, 1)


def advance(start: date, unit: str, count: int) -> date:
    """Move a period start by a signed number of whole periods."""
    if unit == "day":
        return start + timedelta(days=count)
    if unit == "week":
        return start + timedelta(days=7 * count)
    return shift_months(start, _MONTHS[unit] * count)


def extract_atoms(text: str, reference: date) -> list[TimeAtom]:
    """Return the longest nonoverlapping period atoms ordered by position."""
    found: list[TimeAtom] = []
    for pattern, kind in _CALENDAR:
        found.extend(
            atom
            for hit in pattern.finditer(text)
            if (atom := _calendar_atom(hit, kind, text)) is not None
        )
    for pattern, builder in _RELATIVE_BUILDERS:
        found.extend(
            atom for hit in pattern.finditer(text) if (atom := builder(hit, reference)) is not None
        )
    selected: list[TimeAtom] = []
    for atom in sorted(found, key=lambda item: (item.start - item.end, item.start)):
        if all(atom.end <= item.start or atom.start >= item.end for item in selected):
            selected.append(atom)
    return sorted(selected, key=lambda item: item.start)


def _number(value: str) -> int:
    lowered = value.casefold()
    if lowered.isdigit():
        return int(lowered)
    return vocab.NUMBER_WORDS.get(lowered) or vocab.CHINESE_NUMBERS[value]


def _calendar_atom(hit: re.Match[str], kind: str, text: str) -> TimeAtom | None:
    groups = {key: value for key, value in hit.groupdict().items() if value is not None}
    if (
        groups.get("mon", "").casefold() == "may"
        and "year" not in groups
        and text[hit.start("mon") : hit.end("mon")] != "May"
    ):
        return None
    year = int(groups["year"]) if "year" in groups else None
    if kind == "months":
        first, months = int(groups["m1"]), int(groups["m2"]) - int(groups["m1"]) + 1
    elif kind in {"day", "month"}:
        first, months = _month(groups), 1
    elif kind == "quarter":
        quarter = (
            _number(groups["q"]) if "q" in groups else vocab.ORDINALS[groups["ord"].casefold()]
        )
        first, months = quarter * 3 - 2, 3
    elif kind == "half":
        half = _half(groups)
        first, months = half * 6 - 5, 6
    else:
        first, months = 1, 12
    day = int(groups["day"]) if kind == "day" else None
    valid = 1 <= first <= first + months - 1 <= 12  # noqa: PLR2004
    return TimeAtom(
        start=hit.start(),
        end=hit.end(),
        kind=kind,
        year=year,
        month=first if valid else 1,
        day=day,
        months=months if valid else 1,
        issue=None if valid else "Invalid time expression",
    )


def _month(groups: dict[str, str]) -> int:
    if "mon" in groups:
        return vocab.MONTH_NUMBERS[groups["mon"].casefold()[:3]]
    return _number(groups["mm"])


def _half(groups: dict[str, str]) -> int:
    if "hn" in groups:
        return int(groups["hn"])
    if "ch" in groups:
        return 1 if groups["ch"] == "上" else 2
    return vocab.ORDINALS[groups["h"].casefold()]


def _span(
    hit: re.Match[str], kind: str, start: date, end: date, issue: str | None = None
) -> TimeAtom:
    return TimeAtom(
        start=hit.start(),
        end=hit.end(),
        kind=kind,
        interval_start=start,
        interval_end=end,
        issue=issue,
    )


def _relative_en(hit: re.Match[str], reference: date) -> TimeAtom:
    unit, relation = hit.group("unit").casefold(), hit.group("rel").casefold()
    if relation == "past":
        return _span(hit, f"past_{unit}", advance(reference, unit, -1), reference)
    return _relative(hit, reference, unit, _EN_OFFSETS[relation])


def _relative_cn(hit: re.Match[str], reference: date) -> TimeAtom | None:
    prefix = hit.group("prefix").rstrip("个一")
    prefix = "上上" if prefix.startswith("上上") else prefix[:1]
    unit = _CN_UNITS[hit.group("unit")]
    if unit not in _CN_VALID[prefix]:
        return None
    return _relative(hit, reference, unit, _CN_OFFSETS[prefix])


def _relative(hit: re.Match[str], reference: date, unit: str, offset: int) -> TimeAtom:
    start = advance(period_start(reference, unit), unit, offset)
    names = {-2: "before_last", -1: "last", 0: "this", 1: "next"}
    issue = FUTURE_ISSUE if offset > 0 else None
    return _span(hit, f"{names[offset]}_{unit}", start, advance(start, unit, 1), issue)


def _to_date(hit: re.Match[str], reference: date) -> TimeAtom:
    abbreviations = {"y": "year", "m": "month", "q": "quarter", "w": "week"}
    unit = (hit.group("unit") or abbreviations[hit.group("abbr")[0].casefold()]).casefold()
    start = period_start(reference, unit)
    if start >= reference:
        return _span(
            hit, f"{unit}_to_date", start, start + timedelta(days=1), "Empty period to date"
        )
    return _span(hit, f"{unit}_to_date", start, reference)


def _day_word(hit: re.Match[str], reference: date) -> TimeAtom:
    word = (hit.group("word") or hit.group("cn")).casefold()
    offset = _DAY_OFFSETS[word]
    start = reference + timedelta(days=offset)
    return _span(hit, "day", start, start + timedelta(days=1), FUTURE_ISSUE if offset > 0 else None)


def _trailing(hit: re.Match[str], reference: date) -> TimeAtom:
    count = _number(hit.group("n"))
    raw = hit.group("unit").casefold().rstrip("s")
    unit = _CN_UNITS.get(raw, raw)
    days = (reference - advance(reference, unit, -count)).days if count > 0 else 0
    kind = "recent_days" if unit == "day" else f"recent_{unit}s"
    if not 1 <= days <= _MAX_DAYS:
        return _span(hit, kind, reference, reference + timedelta(days=1), "Invalid time expression")
    return _span(hit, kind, advance(reference, unit, -count), reference)


_RELATIVE_BUILDERS: tuple[
    tuple[re.Pattern[str], Callable[[re.Match[str], date], TimeAtom | None]], ...
] = (
    (_RELATIVE_EN, _relative_en),
    (_RELATIVE_CN, _relative_cn),
    (_TO_DATE, _to_date),
    (_DAY_WORD, _day_word),
    (_TRAILING_EN, _trailing),
    (_TRAILING_CN, _trailing),
)
