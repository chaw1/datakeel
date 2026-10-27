# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Dependency-free UTC cron matching with standard five-field semantics."""

from datetime import datetime

from datakeel.core.errors import ValidationError

_SUNDAY_ALIAS = 7
_LIMITS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


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


def validate_cron(expression: str) -> str:
    """Validate numeric five-field cron, returning its canonical spacing."""
    parts = expression.split()
    if len(parts) != len(_LIMITS):
        msg = "Cron requires minute, hour, day, month and weekday fields"
        raise ValidationError(msg)
    try:
        for part, (low, high) in zip(parts, _LIMITS, strict=True):
            _field(part, low, high)
    except ValueError as exc:
        msg = "Invalid numeric cron range or step"
        raise ValidationError(msg) from exc
    return " ".join(parts)


def cron_matches(expression: str, now: datetime) -> bool:
    """Match a UTC minute, OR-ing restricted day-of-month and weekday fields."""
    parts = validate_cron(expression).split()
    fields = tuple(_field(part, *limits) for part, limits in zip(parts, _LIMITS, strict=True))
    weekday = (now.weekday() + 1) % 7
    day_match = now.day in fields[2]
    week_match = weekday in fields[4] or (weekday == 0 and _SUNDAY_ALIAS in fields[4])
    date_match = (
        day_match or week_match if parts[2] != "*" and parts[4] != "*" else day_match and week_match
    )
    return (
        now.minute in fields[0] and now.hour in fields[1] and now.month in fields[3] and date_match
    )
