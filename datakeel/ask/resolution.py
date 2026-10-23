# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic candidate resolution that never turns missing evidence into a guess."""

from difflib import SequenceMatcher

from datakeel.core.ask_models import MetricResolution, ParsedQuestion
from datakeel.core.metric_models import MetricCard

_RANK = {"exact": 3, "synonym": 2, "prefix": 1}
_SUGGESTION_LIMIT = 3


def resolve_metric(
    parsed: ParsedQuestion, cards: list[MetricCard], metric_id: str | None = None
) -> MetricResolution:
    """Select the uniquely strongest registered candidate or request clarification."""
    scores: dict[str, int] = {}
    for match in parsed.matches:
        if match.metric_id:
            scores[match.metric_id] = max(
                scores.get(match.metric_id, 0), _RANK.get(match.match_kind, 0)
            )
    if metric_id is not None:
        return _pinned_metric(parsed, cards, metric_id)
    if not scores:
        return MetricResolution(
            status="unanswerable",
            candidates=nearest_metrics(parsed.question, cards),
            message="无法用已登记指标回答。以下是最接近的指标。",
        )
    strongest = max(scores.values())
    candidates = tuple(
        sorted(
            (card for card in cards if scores.get(card.definition.id) == strongest),
            key=lambda card: card.definition.id,
        )
    )
    if len(candidates) > 1:
        return MetricResolution(
            status="clarification",
            candidates=candidates,
            message="问题对应多个指标。请选择需要的指标口径。",
        )
    if not candidates or candidates[0].status != "resolved":
        return MetricResolution(
            status="unanswerable",
            candidates=candidates,
            message="指标引用的目录对象尚未解析。无法执行问数。",
        )
    if parsed.issues:
        return MetricResolution(
            status="unanswerable",
            candidates=candidates,
            message="无法可靠解析时间条件: " + "; ".join(parsed.issues),
        )
    return MetricResolution(status="resolved", candidates=candidates, message="已定位登记指标。")


def _pinned_metric(
    parsed: ParsedQuestion, cards: list[MetricCard], metric_id: str
) -> MetricResolution:
    candidates = tuple(card for card in cards if card.definition.id == metric_id)
    if not candidates:
        return MetricResolution(
            status="unanswerable",
            candidates=nearest_metrics(parsed.question, cards),
            message="选定指标不存在。请选择已登记指标。",
        )
    if candidates[0].status != "resolved" or parsed.issues or not parsed.matches:
        return MetricResolution(
            status="unanswerable",
            candidates=candidates,
            message="选定指标或问题条件尚未解析。无法执行问数。",
        )
    return MetricResolution(
        status="resolved", candidates=candidates, message="已使用明确选定的指标。"
    )


def nearest_metrics(question: str, cards: list[MetricCard]) -> tuple[MetricCard, ...]:
    """Return at most three stable suggestions without asserting any answer value."""

    def similarity(card: MetricCard) -> float:
        labels = [card.definition.name, *card.definition.synonyms]
        return max(
            SequenceMatcher(None, question.casefold(), label.casefold()).ratio() for label in labels
        )

    ordered = sorted(cards, key=lambda card: (-similarity(card), card.definition.id))
    return tuple(ordered[:_SUGGESTION_LIMIT])
