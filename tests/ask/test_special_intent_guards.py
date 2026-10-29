# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Negated edits and extra calculations cannot be consumed as positive query intent."""

from datetime import UTC, datetime

from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskAnswer, AskRequest
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


def test_negated_special_intents_in_complete_questions_clarify_without_numbers(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """A standalone question cannot invert an explicit refusal into a chart or comparison."""
    for question in (
        "上个季度零售额不要按月拆开",
        "上个季度零售额不要同比",
        "last quarter retail revenue, not by month",
        "last quarter retail revenue, no year over year",
    ):
        answer = _ask(db, question)
        assert answer.status == "clarification", (question, answer.message)
        assert answer.result is None
        assert answer.sql is None
        assert answer.comparison is None


def test_negated_followup_edits_do_not_change_the_last_accepted_frame(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """Rejected bilingual edits keep the accepted metric, time, region and grouping intact."""
    first = _ask(db, "上个季度华东零售额")
    assert first.status == "answered"
    for question in (
        "不要按月拆开",
        "不要同比",
        "不要换成订单数",
        "not by month",
        "do not compare with last year",
        "don't switch to order count",
    ):
        refused = _ask(db, question, first)
        assert refused.status == "clarification", (question, refused.message)
        assert refused.result is None
        assert refused.query_frame == first.query_frame
    resumed = _ask(db, "上个月呢", first)
    complete = _ask(db, "上个月华东零售额")
    assert resumed.status == complete.status == "answered"
    assert resumed.result == complete.result
    assert resumed.query_frame == complete.query_frame


def test_positive_special_intents_do_not_hide_extra_unsupported_calculations(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """Recognizing a chart grain or comparison leaves other arithmetic subject to P12 guards."""
    for question in (
        "上个季度每月零售额的中位数是多少",
        "上个季度零售额同比增长率",
        "last quarter average retail revenue by month",
        "last quarter median retail revenue year over year",
    ):
        answer = _ask(db, question)
        assert answer.status != "answered", (question, answer.message)
        assert answer.result is None
        assert answer.sql is None
