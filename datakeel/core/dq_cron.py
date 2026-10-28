# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Dependency-free UTC cron matching with standard five-field semantics."""

from datetime import datetime, timedelta
from typing import NamedTuple

from datakeel.core.errors import ValidationError

_SUNDAY_ALIAS = 7
_LIMITS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
_MINUTE = timedelta(minutes=1)


class _Schedule(NamedTuple):
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]
    either_day: bool


def _field(expression: str, low: int, high: int) -> frozenset[int]:
    values: set[int] = set()
    for part in expression.split(","):
        base, separator, increment = part.partition("/")
        step = int(increment) if separator else 1
        if step < 1 or step > high - low + 1:
            raise ValueError
        if base == "*":
            start, end = low, high
        elif "-" in base:
            begin, finish = base.split("-", 1)
            start, end = int(begin), int(finish)
        else:
            start = int(base)
            end = high if separator else start
        if not low <= start <= end <= high:
            raise ValueError
        values.update(range(start, end + 1, step))
    return frozenset(values)


def _compile(expression: str) -> _Schedule:
    parts = expression.split()
    if len(parts) != len(_LIMITS):
        msg = "Cron requires minute, hour, day, month and weekday fields"
        raise ValidationError(msg)
    try:
        fields = tuple(_field(part, *limits) for part, limits in zip(parts, _LIMITS, strict=True))
    except ValueError as exc:
        msg = "Invalid numeric cron range or step"
        raise ValidationError(msg) from exc
    return _Schedule(*fields, either_day=parts[2] != "*" and parts[4] != "*")


def _date_matches(schedule: _Schedule, moment: datetime) -> bool:
    weekday = (moment.weekday() + 1) % 7
    day_match = moment.day in schedule.days
    week_match = weekday in schedule.weekdays or (
        weekday == 0 and _SUNDAY_ALIAS in schedule.weekdays
    )
    date_match = (day_match or week_match) if schedule.either_day else day_match and week_match
    return moment.month in schedule.months and date_match


def validate_cron(expression: str) -> str:
    """Validate numeric five-field cron, returning its canonical spacing."""
    _compile(expression)
    return " ".join(expression.split())


def cron_matches(expression: str, now: datetime) -> bool:
    """Match a UTC minute, OR-ing restricted day-of-month and weekday fields."""
    schedule = _compile(expression)
    return (
        _date_matches(schedule, now)
        and now.hour in schedule.hours
        and (now.minute in schedule.minutes)
    )


def latest_match(expression: str, latest: datetime, earliest: datetime) -> datetime | None:
    """Return the newest matching minute in [earliest, latest], skipping whole days and hours."""
    schedule = _compile(expression)
    candidate = latest.replace(second=0, microsecond=0)
    while candidate >= earliest:
        if not _date_matches(schedule, candidate):
            candidate = candidate.replace(hour=0, minute=0) - _MINUTE
        elif candidate.hour not in schedule.hours:
            candidate = candidate.replace(minute=0) - _MINUTE
        elif candidate.minute not in schedule.minutes:
            candidate -= _MINUTE
        else:
            return candidate
    return None
