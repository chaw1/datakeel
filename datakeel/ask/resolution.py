# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic candidate resolution that never turns missing evidence into a guess."""

from difflib import SequenceMatcher

from datakeel.ask.generic import generic_candidates
from datakeel.ask.reasons import refusal
from datakeel.core.ask_models import MatchEvidence, MetricResolution, ParsedQuestion
from datakeel.core.metric_models import MetricCard

_RANK = {"exact": 3, "synonym": 3, "normalized": 2, "prefix": 1}
_SUGGESTION_LIMIT = 3


def resolve_metric(
    parsed: ParsedQuestion, cards: list[MetricCard], metric_id: str | None = None
) -> MetricResolution:
    """Select the uniquely strongest registered candidate or request clarification."""
    scores: dict[str, int] = {}
    for match in _outermost(parsed.matches):
        if match.metric_id:
            scores[match.metric_id] = max(
                scores.get(match.metric_id, 0), _RANK.get(match.match_kind, 0)
            )
    if metric_id is not None:
        return _pinned_metric(parsed, cards, metric_id)
    if not scores:
        return _unscored(parsed, cards)
    strongest = max(scores.values())
    candidates = tuple(
        sorted(
            (card for card in cards if scores.get(card.definition.id) == strongest),
            key=lambda card: card.definition.id,
        )
    )
    if len(candidates) > 1:
        return refusal("clarification", candidates, "ambiguous_metric")
    if not candidates or candidates[0].status != "resolved":
        return refusal("unanswerable", candidates, "unresolved_metric")
    if parsed.issues:
        return refusal("unanswerable", candidates, "time_unparsed", notes=parsed.issues)
    return MetricResolution(status="resolved", candidates=candidates, message="已定位登记指标。")


def _unscored(parsed: ParsedQuestion, cards: list[MetricCard]) -> MetricResolution:
    """Clarify generic heads such as amount or 金额; otherwise suggest the nearest metrics."""
    generic = generic_candidates(parsed.question, parsed.matches, cards)
    if generic:
        return refusal("clarification", generic, "generic_metric")
    return refusal("unanswerable", nearest_metrics(parsed.question, cards), "no_metric")


def _outermost(matches: tuple[MatchEvidence, ...]) -> list[MatchEvidence]:
    """Prefer a complete registered phrase over shorter phrases nested inside it."""
    metric = [item for item in matches if item.metric_id]
    return [
        item
        for item in metric
        if not any(
            other.start <= item.start
            and item.end <= other.end
            and other.end - other.start > item.end - item.start
            and other.metric_id != item.metric_id
            for other in metric
        )
    ]


def _pinned_metric(
    parsed: ParsedQuestion, cards: list[MetricCard], metric_id: str
) -> MetricResolution:
    candidates = tuple(card for card in cards if card.definition.id == metric_id)
    if not candidates:
        return refusal(
            "unanswerable", nearest_metrics(parsed.question, cards), "selected_metric_missing"
        )
    if candidates[0].status != "resolved" or parsed.issues or not parsed.matches:
        return refusal("unanswerable", candidates, "selected_metric_unresolved")
    return MetricResolution(
        status="resolved", candidates=candidates, message="已使用明确选定的指标。"
    )


def nearest_metrics(question: str, cards: list[MetricCard]) -> tuple[MetricCard, ...]:
    """Return at most three stable suggestions without asserting any answer value."""

    def similarity(card: MetricCard) -> float:
        labels = [card.definition.name, card.definition.id, *card.definition.synonyms]
        if card.definition.english_name:
            labels.append(card.definition.english_name)
        return max(
            SequenceMatcher(None, question.casefold(), label.casefold()).ratio() for label in labels
        )

    ordered = sorted(cards, key=lambda card: (-similarity(card), card.definition.id))
    return tuple(ordered[:_SUGGESTION_LIMIT])
