# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent benchmark matching, deliberately separate from product entity identity."""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datakeel.core.kg_eval_models import KGCase, ScoredRelation

MINIMUM_ALIAS_LENGTH = 2
MINIMUM_CONTAINMENT_RATIO = 0.5


def norm(value: str) -> str:
    """Apply the original benchmark's NFKC, prefix, whitespace, and punctuation rules."""
    value = unicodedata.normalize("NFKC", value).strip().lower()
    value = re.sub(r"^(the|dr\.|its|their)\s+", "", value)
    value = re.sub(r"\s+", "", value)
    return value.strip("\"'\u201c\u201d\u2018\u2019.,;:\uff0c\u3002\uff1b\uff1a\u3001")


def match_entity(predicted: str, case: KGCase, type_hint: str | None = None) -> str | None:
    """Match aliases exactly, then rank containment by ratio, type, length, and name."""
    predicted = norm(predicted)
    if not predicted:
        return None
    for entity in case.entities:
        if any(predicted == norm(alias) for alias in (entity.name, *entity.aliases)):
            return entity.name
    best: tuple[float, int, int, str] | None = None
    for entity in case.entities:
        for alias in (entity.name, *entity.aliases):
            normalized = norm(alias)
            if len(normalized) < MINIMUM_ALIAS_LENGTH or not (
                normalized in predicted or predicted in normalized
            ):
                continue
            score = min(len(normalized), len(predicted)) / max(len(normalized), len(predicted))
            if score < MINIMUM_CONTAINMENT_RATIO:
                continue
            key = (score, int(type_hint == entity.type), len(normalized), entity.name)
            if best is None or key > best:
                best = key
    return best[3] if best else None


def located(text: str, value: str) -> bool:
    """Use benchmark normalization, without borrowing product anchoring rules."""
    return norm(value) in norm(text) if norm(value) else False


def span_ok(text: str, start: int | None, end: int | None, expected: str | None) -> bool:
    """Check the benchmark's source-span convention with explicit bounds."""
    return bool(
        expected
        and start is not None
        and end is not None
        and 0 <= start < end <= len(text)
        and norm(text[start:end]) == norm(expected)
    )


def evidence_located(text: str, relation: ScoredRelation) -> bool:
    """Preserve the original evidence-or-two-endpoint-spans measurement."""
    head_span = relation.head_span or (None, None)
    tail_span = relation.tail_span or (None, None)
    return span_ok(text, relation.ev_start, relation.ev_end, relation.evidence) or (
        span_ok(text, *head_span, relation.head) and span_ok(text, *tail_span, relation.tail)
    )


def verified(text: str, relation: ScoredRelation) -> bool:
    """Apply original recording gating, or use the product pipeline's declared verification."""
    if relation.verification is not None:
        return relation.verification == "verified"
    if not (located(text, relation.head) and located(text, relation.tail)):
        return False
    if relation.evidence is not None:
        start, end = relation.ev_start, relation.ev_end
        return (
            start is not None
            and end is not None
            and norm(text[start:end]) == norm(relation.evidence)
        )
    return True
