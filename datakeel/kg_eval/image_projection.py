# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Project persisted image assertions into the independent benchmark's score boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.evidence_models import ImageRegion
from datakeel.core.kg_eval_models import ScoredEntity, ScoredRelation
from datakeel.core.models import AssetRef

if TYPE_CHECKING:
    from datakeel.core.evidence_models import Assertion
    from datakeel.core.kg_product import ProductExtraction


def image_predictions(
    assertions: tuple[Assertion, ...], product: ProductExtraction, text: str
) -> tuple[tuple[ScoredEntity, ...], tuple[ScoredRelation, ...]]:
    """Score only read-back assertions and preserve all retained image region geometry."""
    names = {entity.asset_ref.asset_id: entity.name for entity in product.entities}
    relations: list[ScoredRelation] = []
    for assertion in assertions:
        if assertion.predicate == "kg.mentions" or not isinstance(assertion.object, AssetRef):
            continue
        detail = assertion.verification_detail
        evidence = detail.evidence if detail else None
        relations.append(
            ScoredRelation(
                head=names[assertion.subject.asset_id],
                relation=str(assertion.predicate).removeprefix("kg."),
                tail=names[assertion.object.asset_id],
                evidence=text[evidence.start : evidence.end] if evidence else None,
                ev_start=evidence.start if evidence else None,
                ev_end=evidence.end if evidence else None,
                verification=assertion.verification,
                regions=tuple(
                    anchor.selector.bbox
                    for anchor in assertion.anchors
                    if isinstance(anchor.selector, ImageRegion)
                ),
            )
        )
    mentioned = {item.subject.asset_id for item in assertions if item.predicate == "kg.mentions"}
    entities = tuple(
        ScoredEntity(name=entity.name, type=entity.type)
        for entity in product.entities
        if entity.asset_ref.asset_id in mentioned
    )
    return entities, tuple(relations)
