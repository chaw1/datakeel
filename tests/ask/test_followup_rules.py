# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Pure frame rules exercise calendar-relative edits and cautious inherited resolution."""

from datetime import UTC, date, datetime

from datakeel.ask.followup import prepare_metric_turn
from datakeel.ask.followup_cues import (
    comparison_hits,
    conflicting_edits,
    continuation_spans,
    edit_cue,
    fresh_question,
)
from datakeel.ask.parser import parse_question
from datakeel.core.ask_frame_models import AskQueryFrame
from datakeel.core.ask_models import AskRequest
from datakeel.core.metric_models import DimensionSlice, MetricCard, SemanticLayer, TimeRange

REFERENCE = datetime(2026, 10, 1, tzinfo=UTC)


def _previous() -> AskQueryFrame:
    return AskQueryFrame(
        metric_id="retail_revenue",
        time_range=TimeRange(start=date(2026, 7, 1), end=date(2026, 10, 1)),
        time_basis="period",
        slices=(DimensionSlice(dimension_id="retail_region", value="华东"),),
    )


def test_same_period_last_year_changes_dates_without_requesting_a_comparison(
    layer: SemanticLayer,
) -> None:
    """A bare relative time phrase selects the earlier period rather than a growth calculation."""
    cards = [MetricCard(definition=metric) for metric in layer.metrics]
    for question in ("去年同期", "去年同期呢", "same period last year"):
        turn = prepare_metric_turn(
            AskRequest(question=question, reference_instant=REFERENCE), layer, cards, _previous()
        )
        assert turn.resolution.status == "resolved"
        assert turn.frame
        assert turn.frame.time_range == TimeRange(start=date(2025, 7, 1), end=date(2025, 10, 1))
        assert turn.frame.comparison is None
        assert turn.frame.slices == _previous().slices


def test_missing_or_unresolved_previous_metric_requires_clarification(layer: SemanticLayer) -> None:
    """A saved frame never overrides the current metric catalog's resolution status."""
    request = AskRequest(question="那华南呢", reference_instant=REFERENCE)
    missing = prepare_metric_turn(request, layer, [], _previous())
    assert missing.resolution.status == "clarification"
    unresolved = [
        MetricCard(definition=metric, status="unresolved", reasons=["Missing column"])
        for metric in layer.metrics
    ]
    turn = prepare_metric_turn(request, layer, unresolved, _previous())
    assert turn.resolution.status == "clarification"
    assert turn.frame is None


def test_bare_metric_particle_inherits_but_complete_time_question_resets(
    layer: SemanticLayer,
) -> None:
    """The particle alone does not decide whether the user supplied a fresh complete question."""
    cards = [MetricCard(definition=metric) for metric in layer.metrics]
    followup = prepare_metric_turn(
        AskRequest(question="订单数呢", reference_instant=REFERENCE), layer, cards, _previous()
    )
    assert followup.frame
    assert followup.frame.slices == _previous().slices
    complete = prepare_metric_turn(
        AskRequest(question="上个月订单数是多少呢", reference_instant=REFERENCE),
        layer,
        cards,
        _previous(),
    )
    assert complete.frame
    assert complete.frame.slices == ()
    assert complete.frame.time_range == TimeRange(start=date(2026, 9, 1), end=date(2026, 10, 1))


def test_article_before_last_year_preserves_the_original_temporal_parse(
    layer: SemanticLayer,
) -> None:
    """Articles in ordinary date phrases never introduce an implicit comparison."""
    cards = [MetricCard(definition=metric) for metric in layer.metrics]
    for lead in ("in", "for", "over", "during"):
        request = AskRequest(
            question=f"retail revenue {lead} the last year", reference_instant=REFERENCE
        )
        original = parse_question(request, layer)
        turn = prepare_metric_turn(request, layer, cards, None)
        assert turn.parsed.time_range == original.time_range
        assert turn.parsed.issues == original.issues == ()
        assert turn.frame
        assert turn.frame.time_range == TimeRange(start=date(2025, 1, 1), end=date(2026, 1, 1))
        assert turn.frame.comparison is None
        assert comparison_hits(request.question) == ()


def test_explicit_comparisons_retain_articles_and_relative_period_descriptions() -> None:
    """Only a bare year is excluded; explicit baseline and same-period phrases remain recognized."""
    for question in (
        "compare with the last year",
        "compared to the last year",
        "same period last year",
    ):
        assert [mode for mode, _ in comparison_hits(question)] == ["year_over_year"]
    assert not conflicting_edits("retail revenue for the last year, month over month")
    assert conflicting_edits("compare with the last year, month over month")


def test_same_period_followup_requires_a_prior_bounded_interval(layer: SemanticLayer) -> None:
    """A relative same-period request cannot invent dates for an unbounded prior query."""
    cards = [MetricCard(definition=metric) for metric in layer.metrics]
    unbounded = _previous().model_copy(update={"time_range": None, "time_basis": None})
    cumulative = _previous().model_copy(update={"time_basis": "as_of"})
    for previous in (unbounded, cumulative):
        turn = prepare_metric_turn(
            AskRequest(question="去年同期", reference_instant=REFERENCE), layer, cards, previous
        )
        assert turn.resolution.status == "clarification"
        assert "时间区间" in turn.resolution.message


def test_removed_registered_filter_value_cannot_survive_inherited_frames(
    layer: SemanticLayer,
) -> None:
    """A frame saved before a contract-value change cannot reuse an obsolete filter."""
    dimensions = [
        item.model_copy(
            update={
                "values": [value for value in item.values if value != "华东"],
                "value_synonyms": {
                    key: aliases for key, aliases in item.value_synonyms.items() if key != "华东"
                },
            }
        )
        if item.id == "retail_region"
        else item
        for item in layer.dimensions
    ]
    changed = layer.model_copy(update={"dimensions": dimensions})
    turn = prepare_metric_turn(
        AskRequest(question="上个月呢", reference_instant=REFERENCE),
        changed,
        [MetricCard(definition=metric) for metric in changed.metrics],
        _previous(),
    )
    assert turn.resolution.status == "clarification"
    assert turn.follows


def test_sentences_without_edit_cues_never_inherit_the_previous_metric(
    layer: SemanticLayer,
) -> None:
    """An unregistered concept asked mid-conversation resolves exactly like a fresh question."""
    cards = [MetricCard(definition=metric) for metric in layer.metrics]
    for question in (
        "退货率为什么上升",
        "客户满意度如何",
        "下个月市场份额会是多少",
        "how is customer satisfaction this quarter",
    ):
        request = AskRequest(question=question, reference_instant=REFERENCE)
        turn = prepare_metric_turn(request, layer, cards, _previous())
        fresh = prepare_metric_turn(request, layer, cards, None)
        assert not turn.follows, question
        assert turn.resolution.status == fresh.resolution.status == "unanswerable"
        assert turn.resolution.message == fresh.resolution.message
        assert [item.definition.id for item in turn.resolution.candidates] == [
            item.definition.id for item in fresh.resolution.candidates
        ]
        assert turn.frame is None


def test_question_form_sentences_with_cue_words_still_start_fresh(layer: SemanticLayer) -> None:
    """A why/how question that no slot explains is a new topic even when it contains a cue word."""
    cards = [MetricCard(definition=metric) for metric in layer.metrics]
    for question in ("why did brand awareness drop", "其他客户为什么流失", "只看退货率是否合理"):
        assert edit_cue(question), question
        request = AskRequest(question=question, reference_instant=REFERENCE)
        turn = prepare_metric_turn(request, layer, cards, _previous())
        fresh = prepare_metric_turn(request, layer, cards, None)
        assert not turn.follows, question
        assert turn.resolution.status == fresh.resolution.status == "unanswerable"
        assert turn.resolution.message == fresh.resolution.message
        assert [item.definition.id for item in turn.resolution.candidates] == [
            item.definition.id for item in fresh.resolution.candidates
        ]
        assert len(turn.resolution.candidates) == 3
    for question in ("那为什么呢", "why did it drop in August 2026", "上个月多少"):
        turn = prepare_metric_turn(
            AskRequest(question=question, reference_instant=REFERENCE), layer, cards, _previous()
        )
        assert turn.follows, question
        assert turn.resolution.candidates[0].definition.id == _previous().metric_id
    assert fresh_question("why did brand awareness drop", [])
    assert not fresh_question("why did brand awareness drop", [(4, 7)])
    assert not fresh_question("那为什么呢", [])
    assert not fresh_question("再详细点", [])


def test_edit_cues_and_fully_understood_fragments_keep_the_conversation(
    layer: SemanticLayer,
) -> None:
    """Particles, edit verbs, negated edits and bare slots all refer back to the saved frame."""
    cards = [MetricCard(definition=metric) for metric in layer.metrics]
    for question in ("再详细点", "不要同比", "按周拆开", "华南", "上个月", "monthly", "那边呢"):
        turn = prepare_metric_turn(
            AskRequest(question=question, reference_instant=REFERENCE), layer, cards, _previous()
        )
        assert turn.follows, question
    for cued in ("那华南呢", "what about it", "再详细点", "按周拆开", "not by month"):
        assert edit_cue(cued), cued
    for fresh in ("退货率为什么上升", "客户满意度如何", "下个月市场份额会是多少"):
        assert not edit_cue(fresh), fresh
    assert continuation_spans("那华南呢") == [(0, 1), (3, 4)]
    assert continuation_spans("what about August 2026?") == [(0, 10)]
    assert continuation_spans("呢") == [(0, 1)]
    assert continuation_spans("退货率为什么上升") == []


def test_bare_particles_without_an_understood_edit_still_clarify(layer: SemanticLayer) -> None:
    """Consuming the particle never counts as understanding what should change."""
    cards = [MetricCard(definition=metric) for metric in layer.metrics]
    for question in ("那呢", "呢", "what about", "那华南,魔法校正呢"):
        turn = prepare_metric_turn(
            AskRequest(question=question, reference_instant=REFERENCE), layer, cards, _previous()
        )
        assert turn.follows, question
        assert turn.resolution.status == "clarification", question
