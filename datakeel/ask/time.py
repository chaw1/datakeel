# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit UTC calendar intervals for supported business time expressions."""

import re
from datetime import UTC, date, datetime, timedelta

from datakeel.ask.models import TimeParse
from datakeel.core.ask_models import MatchEvidence
from datakeel.core.metric_models import TimeRange

_MONTH = re.compile(r"(?P<year>\d{4})\s*年\s*(?P<month>\d{1,2})\s*月")
_RECENT = re.compile(r"近\s*(?P<days>\d+)\s*天")
_QUARTER = re.compile(r"上(?:个)?季度")
_UNSUPPORTED = re.compile(
    r"今年|去年|明年|本月|上个月|下个月|本季度|下个季度|今天|昨天|明天|\d{4}年"
)
_MAX_RECENT_DAYS = 3650
_MONTHS_PER_YEAR = 12
_MONTHS_PER_QUARTER = 3


def parse_time(question: str, reference_instant: datetime) -> TimeParse:
    """Resolve recognized expressions and refuse conflicting or unsupported time requests."""
    reference = reference_instant.astimezone(UTC).date()
    intervals: list[TimeRange] = []
    matches: list[MatchEvidence] = []
    issues: list[str] = []
    for pattern, kind in ((_MONTH, "month"), (_RECENT, "recent_days"), (_QUARTER, "last_quarter")):
        for hit in pattern.finditer(question):
            try:
                intervals.append(_interval(hit, kind, reference))
            except (ValueError, OverflowError):
                issues.append(f"Invalid time expression: {hit.group()}")
            matches.append(
                MatchEvidence(
                    start=hit.start(),
                    end=hit.end(),
                    text=hit.group(),
                    source=f"time:{kind}",
                    match_kind="time",
                )
            )
    if len(set(intervals)) > 1:
        issues.append("Multiple distinct time intervals require clarification")
    remainder = list(question)
    for match in matches:
        remainder[match.start : match.end] = " " * (match.end - match.start)
    if _UNSUPPORTED.search("".join(remainder)):
        issues.append("Time expression is not supported by the registered parser")
    return TimeParse(
        time_range=intervals[0] if intervals and not issues else None,
        matches=tuple(sorted(matches, key=lambda item: item.start)),
        issues=tuple(issues),
    )


def _interval(hit: re.Match[str], kind: str, reference: date) -> TimeRange:
    if kind == "month":
        year, month = int(hit.group("year")), int(hit.group("month"))
        start = date(year, month, 1)
        end = date(year + month // _MONTHS_PER_YEAR, month % _MONTHS_PER_YEAR + 1, 1)
    elif kind == "recent_days":
        days = int(hit.group("days"))
        if not 1 <= days <= _MAX_RECENT_DAYS:
            msg = "Recent-day intervals must be between 1 and 3650 days"
            raise ValueError(msg)
        start, end = reference - timedelta(days=days), reference
    else:
        quarter_month = (reference.month - 1) // _MONTHS_PER_QUARTER * _MONTHS_PER_QUARTER + 1
        end = date(reference.year, quarter_month, 1)
        start = (
            date(end.year - 1, 10, 1)
            if quarter_month == 1
            else date(end.year, quarter_month - 3, 1)
        )
    return TimeRange(start=start, end=end)
