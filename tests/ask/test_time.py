# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Calendar parsing covers year boundaries, injected instants, and invalid requests."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from datakeel.ask.time import parse_time


@pytest.mark.parametrize(
    ("question", "instant", "start", "end"),
    [
        ("上个季度", datetime(2026, 10, 1, tzinfo=UTC), "2026-07-01", "2026-10-01"),
        ("上季度", datetime(2026, 1, 5, tzinfo=UTC), "2025-10-01", "2026-01-01"),
        ("2026 年 3 月", datetime(2026, 10, 1, tzinfo=UTC), "2026-03-01", "2026-04-01"),
        ("2025年12月", datetime(2026, 10, 1, tzinfo=UTC), "2025-12-01", "2026-01-01"),
        ("近30天", datetime(2026, 10, 1, tzinfo=UTC), "2026-09-01", "2026-10-01"),
        (
            "近1天",
            datetime(2026, 10, 1, 1, tzinfo=timezone(timedelta(hours=8))),
            "2026-09-29",
            "2026-09-30",
        ),
    ],
)
def test_time_ranges_are_half_open_utc_intervals(
    question: str,
    instant: datetime,
    start: str,
    end: str,
) -> None:
    """Resolve each supported expression independently of the host clock and timezone."""
    parsed = parse_time(question, instant)
    assert parsed.issues == ()
    assert parsed.time_range is not None
    assert (parsed.time_range.start.isoformat(), parsed.time_range.end.isoformat()) == (start, end)


@pytest.mark.parametrize(
    "question", ["2026年13月", "2026年0月", "近0天", "近99999天", "今年", "下个月"]
)
def test_invalid_or_unsupported_time_is_not_silently_ignored(question: str) -> None:
    """Unsupported or invalid dates never degrade into an all-time query."""
    parsed = parse_time(question, datetime(2026, 10, 1, tzinfo=UTC))
    assert parsed.issues
    assert parsed.time_range is None


def test_distinct_time_ranges_require_clarification() -> None:
    """Multiple intervals remain explicit instead of arbitrarily choosing the first."""
    parsed = parse_time("2026年3月和2026年4月", datetime(2026, 10, 1, tzinfo=UTC))
    assert parsed.issues == ("Multiple distinct time intervals require clarification",)
