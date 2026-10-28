# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Offer clarification when a question names only a generic measure noun."""

import re

from datakeel.ask.matching import occurrences
from datakeel.core.ask_models import MatchEvidence
from datakeel.core.metric_models import MetricCard

_EN_HEADS = frozenset(
    {
        "amount",
        "amounts",
        "value",
        "values",
        "revenue",
        "revenues",
        "sales",
        "units",
        "unit",
        "quantity",
        "quantities",
        "count",
        "counts",
        "cost",
        "costs",
        "expense",
        "expenses",
        "volume",
        "volumes",
        "total",
        "totals",
    }
)
_CN_HEADS = ("金额", "件数", "数量", "费用", "成本", "收入", "总额", "单量", "销量")


def generic_candidates(
    question: str, matches: tuple[MatchEvidence, ...], cards: list[MetricCard]
) -> tuple[MetricCard, ...]:
    """Return metrics whose registered labels end in a measure noun the question uses alone."""
    remainder = list(question)
    for item in matches:
        remainder[item.start : item.end] = " " * (item.end - item.start)
    text = "".join(remainder)
    candidates = [
        card for card in cards if any(occurrences(text, head) for head in sorted(_heads(card)))
    ]
    return tuple(sorted(candidates, key=lambda card: card.definition.id))


def _heads(card: MetricCard) -> set[str]:
    metric = card.definition
    heads: set[str] = set()
    for label in [metric.name, metric.english_name or "", *metric.synonyms]:
        words = re.findall(r"[A-Za-z]+", label)
        if words and words[-1].casefold() in _EN_HEADS:
            heads.add(words[-1].casefold())
        heads.update(head for head in _CN_HEADS if label.endswith(head))
    return heads
