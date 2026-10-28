# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit baseline month and quarter signals cannot silently become a different period."""

from datetime import UTC, date, datetime

import pytest

from datakeel.ask import service
from datakeel.ask.comparisons import comparison_unit_mismatch
from datakeel.ask.service import ask_data
from datakeel.core.ask_frame_models import AskQueryFrame
from datakeel.core.ask_models import AskAnswer, AskRequest
from datakeel.core.metric_models import TimeRange
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.database import Database

REFERENCE = datetime(2026, 10, 1, tzinfo=UTC)


def _ask(db: Database, question: str, previous: AskAnswer | None = None) -> AskAnswer:
    return ask_data(
        db,
        AskRequest(
            question=question,
            reference_instant=REFERENCE,
            conversation_id=previous.conversation_id if previous else None,
        ),
    )


def test_explicit_baseline_unit_mismatch_clarifies_before_sql_and_preserves_the_accepted_frame(
    db: Database, enterprise_sample: EnterpriseSample, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Explicit baseline units cannot substitute a month for a quarter or vice versa."""
    quarter = _ask(db, "last quarter retail revenue")
    month = _ask(db, "last month retail revenue")
    assert quarter.status == month.status == "answered"

    def forbidden(*_args: object, **_kwargs: object) -> None:
        msg = "A mismatched explicit baseline unit must not execute SQL"
        raise AssertionError(msg)

    monkeypatch.setattr(service, "execute_query", forbidden)
    cases = (
        (quarter, "和上个月比"),
        (quarter, "compare with the previous month"),
        (quarter, "MOM"),
        (quarter, "month over month"),
        (month, "和上个季度比"),
        (month, "compare with the previous quarter"),
        (month, "QOQ"),
        (month, "quarter over quarter"),
    )
    for previous, question in cases:
        answer = _ask(db, question, previous)
        assert answer.status == "clarification", (question, answer.message)
        assert answer.result is None
        assert answer.sql is None
        assert answer.comparison is None
        assert answer.query_frame == previous.query_frame
    for question in (
        "last quarter retail revenue compare with the previous month",
        "上个月零售额和上个季度比",
    ):
        answer = _ask(db, question)
        assert answer.status == "clarification"
        assert answer.result is None
        assert answer.sql is None


def test_matching_explicit_units_and_generic_period_comparisons_keep_the_correct_baselines(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """Matching explicit units and generic POP query the true previous period."""
    quarter = _ask(db, "last quarter retail revenue")
    month = _ask(db, "last month retail revenue")
    previous_quarter = TimeRange(start=date(2026, 4, 1), end=date(2026, 7, 1))
    previous_month = TimeRange(start=date(2026, 8, 1), end=date(2026, 9, 1))
    cases = (
        (quarter, "和上个季度比", previous_quarter),
        (quarter, "compare with the previous quarter", previous_quarter),
        (quarter, "QOQ", previous_quarter),
        (quarter, "quarter over quarter", previous_quarter),
        (quarter, "环比", previous_quarter),
        (quarter, "period over period", previous_quarter),
        (month, "和上个月比", previous_month),
        (month, "compare with the previous month", previous_month),
        (month, "MOM", previous_month),
        (month, "month over month", previous_month),
        (month, "环比", previous_month),
        (month, "period over period", previous_month),
    )
    for previous, question, baseline in cases:
        answer = _ask(db, question, previous)
        assert answer.status == "answered", (question, answer.message)
        assert answer.result == previous.result
        assert answer.comparison
        assert answer.comparison.previous_time_range == baseline


def test_explicit_calendar_units_reject_partial_months_and_unaligned_three_month_windows() -> None:
    """Having the same approximate duration is insufficient for an explicit calendar baseline."""
    partial = AskQueryFrame(
        metric_id="x",
        comparison="period_over_period",
        time_range=TimeRange(start=date(2026, 9, 2), end=date(2026, 10, 2)),
    )
    unaligned = AskQueryFrame(
        metric_id="x",
        comparison="period_over_period",
        time_range=TimeRange(start=date(2026, 2, 1), end=date(2026, 5, 1)),
    )
    assert comparison_unit_mismatch("compare with the previous month", partial)
    assert comparison_unit_mismatch("QOQ", unaligned)
    assert not comparison_unit_mismatch("period over period", partial)
    assert not comparison_unit_mismatch("环比", unaligned)
    assert not comparison_unit_mismatch("MOM", AskQueryFrame(metric_id="x"))
