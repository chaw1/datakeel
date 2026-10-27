# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""English and Chinese time phrases share one parser, one future guard and one answer path."""

from datetime import UTC, datetime

import pytest

from datakeel.ask.service import ask_data
from datakeel.ask.time import parse_time
from datakeel.core.ask_models import AskRequest
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.database import Database

REFERENCE = datetime(2026, 10, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    ("phrase", "start", "end"),
    [
        ("in March 2026", "2026-03-01", "2026-04-01"),
        ("for Mar 2026", "2026-03-01", "2026-04-01"),
        ("in Sept 2026", "2026-09-01", "2026-10-01"),
        ("during February, 2026", "2026-02-01", "2026-03-01"),
        ("Q2 2026", "2026-04-01", "2026-07-01"),
        ("2026 Q2", "2026-04-01", "2026-07-01"),
        ("the second quarter of 2026", "2026-04-01", "2026-07-01"),
        ("the 3rd quarter of 2026", "2026-07-01", "2026-10-01"),
        ("last month", "2026-09-01", "2026-10-01"),
        ("previous quarter", "2026-07-01", "2026-10-01"),
        ("this year", "2026-01-01", "2027-01-01"),
        ("last year", "2025-01-01", "2026-01-01"),
        ("from January 2026 to March 2026", "2026-01-01", "2026-04-01"),
        ("between Feb and Apr 2026", "2026-02-01", "2026-05-01"),
        ("H1 2026", "2026-01-01", "2026-07-01"),
        ("year to date", "2026-01-01", "2026-10-01"),
        ("since April 2026", "2026-04-01", "2026-10-01"),
        ("2026年第三季度", "2026-07-01", "2026-10-01"),
        ("三季度", "2026-07-01", "2026-10-01"),
        ("第2季度", "2026-04-01", "2026-07-01"),
        ("2026年Q3", "2026-07-01", "2026-10-01"),
        ("2026年1-3月", "2026-01-01", "2026-04-01"),
    ],
)
def test_period_phrases_resolve_to_half_open_intervals(phrase: str, start: str, end: str) -> None:
    """Month names, quarter forms, relative periods and ranges resolve against the reference."""
    parsed = parse_time(f"retail revenue {phrase}", REFERENCE)
    assert parsed.issues == ()
    assert parsed.basis == "period"
    assert parsed.time_range is not None
    assert (parsed.time_range.start.isoformat(), parsed.time_range.end.isoformat()) == (start, end)


@pytest.mark.parametrize(
    "phrase",
    [
        "as of the end of June 2026",
        "at the end of June 2026",
        "as of June 2026",
        "截至2026年6月底",
        "2026年6月末",
    ],
)
def test_point_in_time_phrases_share_the_chinese_as_of_semantics(phrase: str) -> None:
    """``as of`` and ``at the end of`` close the interval exactly where 截至 does."""
    parsed = parse_time(phrase, REFERENCE)
    assert parsed.issues == ()
    assert parsed.basis == "as_of"
    assert parsed.time_range is not None
    assert parsed.time_range.end.isoformat() == "2026-07-01"


@pytest.mark.parametrize(
    "phrase",
    ["next month", "this quarter", "Q4 2026", "Q1 2027", "下个月", "明年", "next year"],
)
def test_periods_that_have_not_started_are_refused(phrase: str) -> None:
    """A period starting at or after the reference instant has no data to report."""
    parsed = parse_time(phrase, REFERENCE)
    assert parsed.time_range is None
    assert any(issue.startswith("Future periods are not supported") for issue in parsed.issues)


@pytest.mark.parametrize("phrase", ["March 2026 and April 2026", "2026年3月和2026年4月"])
def test_distinct_periods_require_clarification(phrase: str) -> None:
    """Two different intervals are never collapsed into the first one."""
    parsed = parse_time(phrase, REFERENCE)
    assert parsed.time_range is None
    assert parsed.issues == ("Multiple distinct time intervals require clarification",)


@pytest.mark.parametrize(
    ("english", "chinese"),
    [
        ("retail revenue in March 2026", "2026年3月零售额"),
        ("retail revenue for Q2 2026", "2026年第二季度零售额"),
        ("retail revenue in the third quarter of 2026", "三季度零售额"),
        ("retail revenue last quarter", "上个季度零售额"),
        ("retail revenue from January 2026 to March 2026", "2026年1-3月零售额"),
        ("refund amount last month", "上个月退款额"),
        ("inventory units as of the end of September 2026", "截至2026年9月底库存量"),
    ],
)
def test_english_time_answers_equal_the_chinese_answers(
    db: Database, enterprise_sample: EnterpriseSample, english: str, chinese: str
) -> None:
    """The English path applies the same interval as the Chinese path, never all-time totals."""
    assert enterprise_sample.sources
    reference = AskRequest(question=chinese, reference_instant=REFERENCE)
    expected = ask_data(db, reference)
    answer = ask_data(db, AskRequest(question=english, reference_instant=REFERENCE))
    assert expected.status == answer.status == "answered", (english, answer.message)
    assert answer.result == expected.result
    assert answer.interpretation is not None
    assert expected.interpretation is not None
    assert answer.interpretation.time_range == expected.interpretation.time_range
    everything = ask_data(
        db,
        AskRequest(
            question=answer.metric_card.definition.name if answer.metric_card else english,
            reference_instant=REFERENCE,
        ),
    )
    if answer.interpretation.time_basis == "period":
        assert answer.result != everything.result
