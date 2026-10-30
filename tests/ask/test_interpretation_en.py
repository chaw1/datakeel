# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""An English interface reads the interpretation and subject names without Chinese templates."""

import re
from datetime import UTC, date, datetime

from datakeel.ask.interpretation_en import interpreted_question_en
from datakeel.ask.service import ask_data
from datakeel.core.ask_frame_models import AskQueryFrame
from datakeel.core.ask_models import AskRequest
from datakeel.core.metric_models import TimeRange
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.ask_conversations import get_conversation
from datakeel.storage.database import Database

REFERENCE = datetime(2026, 10, 1, tzinfo=UTC)
CHINESE = re.compile(r"[一-鿿]")


def test_english_interpretation_words_every_slot_with_registered_english_names(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """Metric and dimensions use their English names; only the recorded value stays Chinese."""
    answer = ask_data(
        db,
        AskRequest(question="上个季度华东零售额按零售渠道按月同比", reference_instant=REFERENCE),
    )
    assert answer.status == "answered"
    assert answer.interpreted_question_en == (
        "Query Retail revenue, from 2026-07-01 to 2026-10-01 (end date excluded), "
        "where Retail region is 华东, grouped by Retail channel, split by month, "
        "compared with the same period last year."
    )
    assert not CHINESE.search(answer.interpreted_question_en.replace("华东", ""))
    assert "零售区域为华东" in answer.interpreted_question
    assert answer.conversation_id
    restored = get_conversation(db, answer.conversation_id)
    assert restored.turns[0].interpreted_question_en == answer.interpreted_question_en


def test_english_interpretation_of_shares_and_previous_periods(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """Every optional slot has an English wording; without a frame the question is kept."""
    card = ask_data(
        db, AskRequest(question="零售额是多少", reference_instant=REFERENCE)
    ).metric_card
    frame = AskQueryFrame(
        metric_id="retail_revenue",
        time_range=TimeRange(start=date(2026, 7, 1), end=date(2026, 10, 1)),
        group_by=("unregistered_dimension",),
        time_grain="quarter",
        comparison="period_over_period",
        share_of_result_rows=True,
    )
    assert interpreted_question_en(frame, card, "q") == (
        "Query Retail revenue, from 2026-07-01 to 2026-10-01 (end date excluded), "
        "grouped by unregistered_dimension, split by quarter, compared with the previous "
        "period, showing each row's share of the returned rows' total "
        "(not computed when the total is 0)."
    )
    assert interpreted_question_en(None, None, "零售额是多少") == "零售额是多少"
    assert interpreted_question_en(frame, None, "q") == "q"


def test_recognized_metric_subject_carries_its_registered_english_name(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """The recognition line can name the metric in English; the matched text stays as asked."""
    answer = ask_data(db, AskRequest(question="零售额是多少", reference_instant=REFERENCE))
    assert answer.recognition is not None
    subject = answer.recognition.subjects[0]
    assert subject.text == "零售额"
    assert subject.subject.name == "零售额"
    assert subject.subject.english_name == "Retail revenue"
    assert answer.interpreted_question_en == "Query Retail revenue."
