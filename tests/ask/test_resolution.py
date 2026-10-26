# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Candidate ranking returns clarification or refusal without inventing answers."""

from datakeel.ask.parser import parse_question
from datakeel.ask.resolution import resolve_metric
from datakeel.core.ask_models import AskRequest, MatchEvidence, ParsedQuestion
from datakeel.core.metric_models import MetricCard, SemanticLayer


def test_exact_metric_and_repeated_synonym_resolve_once(layer: SemanticLayer) -> None:
    """Multiple words for the same registered metric form one candidate."""
    parsed = parse_question(AskRequest(question="零售额和终端零售额是多少"), layer)
    result = resolve_metric(parsed, [MetricCard(definition=item) for item in layer.metrics])
    assert result.status == "resolved"
    assert [card.definition.id for card in result.candidates] == ["retail_revenue"]


def test_registered_candidates_share_priority_above_prefix(layer: SemanticLayer) -> None:
    """Registered names and synonyms share a tier and both outrank truncated names."""
    matches = tuple(
        MatchEvidence(
            start=0,
            end=1,
            text="x",
            source="fixture",
            match_kind=kind,
            metric_id=layer.metrics[index].id,
        )
        for index, kind in enumerate(("exact", "synonym", "prefix"))
    )
    result = resolve_metric(
        ParsedQuestion(question="x", matches=matches),
        [MetricCard(definition=item) for item in layer.metrics],
    )
    assert result.status == "clarification"
    assert {card.definition.id for card in result.candidates} == {
        layer.metrics[0].id,
        layer.metrics[1].id,
    }


def test_distinct_exact_candidates_and_shared_synonym_require_clarification(
    layer: SemanticLayer,
) -> None:
    """Two explicit metrics and the deliberately conflicting turnover alias remain ambiguous."""
    cards = [MetricCard(definition=item) for item in layer.metrics]
    for question in ("出货额和零售额是多少", "营业额是多少"):
        result = resolve_metric(parse_question(AskRequest(question=question), layer), cards)
        assert result.status == "clarification"
        assert len(result.candidates) >= 2


def test_unmatched_question_returns_three_suggestions_and_no_selected_metric(
    layer: SemanticLayer,
) -> None:
    """Similarity provides suggestions only after the answer has already been refused."""
    cards = [MetricCard(definition=item) for item in layer.metrics]
    result = resolve_metric(parse_question(AskRequest(question="退货率为什么上升"), layer), cards)
    assert result.status == "unanswerable"
    assert len(result.candidates) == 3


def test_unresolved_metric_unsupported_time_and_missing_candidate_refuse(
    layer: SemanticLayer,
) -> None:
    """Broken references and unsupported temporal requests never reach SQL compilation."""
    parsed = parse_question(AskRequest(question="零售额是多少"), layer)
    broken = [
        MetricCard(definition=item, status="unresolved", reasons=["missing"])
        for item in layer.metrics
    ]
    assert resolve_metric(parsed, broken).status == "unanswerable"
    assert resolve_metric(parsed, []).status == "unanswerable"
    timed = parse_question(AskRequest(question="下个月零售额是多少"), layer)
    assert (
        resolve_metric(timed, [MetricCard(definition=item) for item in layer.metrics]).status
        == "unanswerable"
    )
