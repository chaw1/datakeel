# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Result-row share presentation reuses grouped measures without broadening metric arithmetic."""

from datetime import UTC, datetime

import pytest

from datakeel.ask import service
from datakeel.ask.followup import prepare_metric_turn
from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskAnswer, AskRequest
from datakeel.core.metric_models import MetricCard, SemanticLayer
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.database import Database
from datakeel.storage.metric_store import get_metric, update_metric_in_session

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


def test_grouped_share_preserves_the_original_rows_and_names_the_result_row_denominator(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """Chinese share and English share/proportion use the original grouped SQL and row values."""
    questions = (
        ("上个季度按零售区域零售额占比", "上个季度按零售区域零售额"),
        ("last quarter retail revenue share by region", "last quarter retail revenue by region"),
        (
            "last quarter retail revenue proportion by channel",
            "last quarter retail revenue by channel",
        ),
    )
    for question, original in questions:
        answer, grouped = _ask(db, question), _ask(db, original)
        assert answer.status == grouped.status == "answered", (question, answer.message)
        assert answer.result == grouped.result
        assert answer.sql == grouped.sql
        assert answer.query_frame
        assert answer.query_frame.share_of_result_rows
        assert answer.chart
        assert answer.chart.type == "bar"
        assert answer.chart.show_percent
        assert "分母为当前返回结果行总和" in answer.interpreted_question
        assert "2026-07-01" in answer.interpreted_question
        assert "零售额" in answer.interpreted_question


def test_time_series_share_uses_bars_with_the_same_calendar_rows(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """A share request changes the chart presentation, while its metric rows remain time buckets."""
    answer = _ask(db, "上个季度按月零售额占比")
    grouped = _ask(db, "上个季度按月零售额")
    assert answer.status == grouped.status == "answered"
    assert answer.result == grouped.result
    assert answer.sql == grouped.sql
    assert answer.chart
    assert answer.chart.type == "bar"
    assert answer.chart.show_percent
    assert grouped.chart
    assert grouped.chart.type == "line"


def test_share_followups_inherit_display_intent_and_complete_topics_reset_it(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """Share display survives time/value edits without changing their full-question equivalence."""
    first = _ask(db, "上个季度按零售区域零售额")
    share = _ask(db, "show shares", first)
    assert share.status == "answered"
    assert share.result == first.result
    assert share.chart
    assert share.chart.show_percent
    south = _ask(db, "那华南呢", share)
    september = _ask(db, "上个月呢", south)
    complete = _ask(db, "上个月华南按零售区域零售额占比")
    assert september.status == complete.status == "answered"
    assert september.result == complete.result
    assert september.query_frame == complete.query_frame
    assert september.chart
    assert september.chart.show_percent
    assert "分母为当前返回结果行总和" in september.interpreted_question
    fresh = _ask(db, "上个月订单数是多少", september)
    assert fresh.status == "answered"
    assert fresh.query_frame
    assert not fresh.query_frame.share_of_result_rows
    assert fresh.chart
    assert not fresh.chart.show_percent


def test_share_questions_reject_ungrouped_or_ununderstood_conditions_before_sql(
    db: Database, enterprise_sample: EnterpriseSample, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Share display cannot approve an ungrouped result, negation, other math or unknown filter."""
    first = _ask(db, "上个季度按零售区域零售额")

    def forbidden(*_args: object, **_kwargs: object) -> None:
        msg = "An unsupported share interpretation must fail before SQL execution"
        raise AssertionError(msg)

    monkeypatch.setattr(service, "execute_query", forbidden)
    for question in (
        "零售额占比",
        "retail revenue share",
        "上个季度按零售区域零售额不要占比",
        "上个季度按零售区域零售额占比不需要",
        "last quarter retail revenue by region, no share",
        "last quarter average retail revenue share by region",
        "上个季度按零售区域零售额占比平均",
        "last quarter retail revenue share ratio by region",
        "上个季度按零售区域零售额占比比率",
        "last quarter retail revenue share by region with lunar visibility only",
    ):
        refused = _ask(db, question)
        assert refused.status != "answered", (question, refused.message)
        assert refused.result is None
        assert refused.sql is None
    for question in ("不要占比", "no share", "show share with lunar visibility only"):
        refused = _ask(db, question, first)
        assert refused.status == "clarification", (question, refused.message)
        assert refused.result is None
        assert refused.query_frame == first.query_frame


def test_registered_metric_names_containing_share_are_never_rewritten_as_display_intent(
    layer: SemanticLayer,
) -> None:
    """A registered measure called share remains its own metric, without implicit grouping."""
    replacement = layer.metrics[0].model_copy(
        update={"name": "登记占比", "english_name": "Registered share"}
    )
    changed = layer.model_copy(update={"metrics": [replacement, *layer.metrics[1:]]})
    cards = [MetricCard(definition=metric) for metric in changed.metrics]
    for question in ("登记占比", "Registered share"):
        turn = prepare_metric_turn(
            AskRequest(question=question, reference_instant=REFERENCE), changed, cards, None
        )
        assert turn.resolution.status == "resolved"
        assert turn.frame
        assert not turn.frame.share_of_result_rows


def test_registered_share_metric_name_does_not_enable_a_share_display(
    db: Database, enterprise_sample: EnterpriseSample
) -> None:
    """A registered measure with share in its name retains its original scalar presentation."""
    card = get_metric(db, "retail_revenue")
    with db.session() as session:
        update_metric_in_session(
            session,
            card.definition.model_copy(
                update={"name": "登记占比", "english_name": "Registered share"}
            ),
        )
        session.commit()
    answer = _ask(db, "Registered share")
    assert answer.status == "answered"
    assert answer.query_frame
    assert not answer.query_frame.share_of_result_rows
    assert answer.chart
    assert answer.chart.type == "scalar"
    assert not answer.chart.show_percent
