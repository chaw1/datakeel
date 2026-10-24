# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Translate actual production candidates into the independent scorer's input boundary."""

from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING

from datakeel.core.kg_eval_models import KGBlockedRelation, ScoredEntity, ScoredRelation
from datakeel.core.models import AssetRef
from datakeel.kg.identity import merge_drafts

if TYPE_CHECKING:
    from datakeel.core.evidence_drafts import ObservationDraft
    from datakeel.core.kg_models import RawExtraction
    from datakeel.core.kg_product import ProductExtraction


def _span(text: str, quote: str) -> tuple[int | None, int | None]:
    if not quote:
        return None, None
    start = text.find(quote)
    if start >= 0:
        return start, start + len(quote)
    chars: list[str] = []
    offsets: list[int] = []
    for index, char in enumerate(text):
        for normalized in unicodedata.normalize("NFKC", char).lower():
            if not normalized.isspace():
                chars.append(normalized)
                offsets.append(index)
    needle = "".join(unicodedata.normalize("NFKC", quote).lower().split())
    found = "".join(chars).find(needle) if needle else -1
    if found < 0:
        return None, None
    return offsets[found], offsets[found + len(needle) - 1] + 1


def raw_relations(raw: RawExtraction, text: str) -> tuple[ScoredRelation, ...]:
    """Locate fresh raw evidence without borrowing product identity or verification."""
    result: list[ScoredRelation] = []
    for relation in raw.relations:
        start, end = _span(text, relation.evidence)
        result.append(
            ScoredRelation(
                head=relation.head,
                relation=relation.relation,
                tail=relation.tail,
                evidence=relation.evidence,
                ev_start=start,
                ev_end=end,
            )
        )
    return tuple(result)


def _relation(draft: ObservationDraft, names: dict[str, str], text: str) -> ScoredRelation | None:
    if draft.predicate == "kg.mentions" or not isinstance(draft.object, AssetRef):
        return None
    detail = draft.verification_detail
    evidence = detail.evidence if detail else None
    return ScoredRelation(
        head=names[draft.subject.asset_id],
        relation=str(draft.predicate).removeprefix("kg."),
        tail=names[draft.object.asset_id],
        evidence=text[evidence.start : evidence.end] if evidence else None,
        ev_start=evidence.start if evidence else None,
        ev_end=evidence.end if evidence else None,
        verification=draft.verification,
    )


def product_predictions(
    products: tuple[ProductExtraction, ...], text: str
) -> tuple[tuple[ScoredEntity, ...], tuple[ScoredRelation, ...]]:
    """Score the merged production drafts, including all needs-review candidates."""
    entities = {entity.asset_ref.asset_id: entity for item in products for entity in item.entities}
    names = {key: entity.name for key, entity in entities.items()}
    drafts = merge_drafts(tuple(draft for item in products for draft in item.drafts))
    relations = tuple(
        relation for draft in drafts if (relation := _relation(draft, names, text)) is not None
    )
    return tuple(
        ScoredEntity(name=item.name, type=item.type) for item in entities.values()
    ), relations


def blocked_relations(
    case_id: str, products: tuple[ProductExtraction, ...]
) -> tuple[KGBlockedRelation, ...]:
    """Retain each excluded relation and the production pipeline's reason."""
    return tuple(
        KGBlockedRelation(
            case_id=case_id,
            head=sample.head,
            relation=sample.relation,
            tail=sample.tail,
            evidence=sample.evidence,
            reason=proposal.reason,
        )
        for product in products
        for proposal in product.proposals
        for sample in proposal.samples
    )
