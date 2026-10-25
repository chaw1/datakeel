# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Add image coordinates and structured review rules to ordinary text graph products."""

from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_models import (
    EvidenceAnchor,
    ImageRegion,
    VerificationDetail,
    VerificationIssue,
    Whole,
)
from datakeel.core.kg_contracts import KGSchema
from datakeel.core.kg_execution import KGDocument
from datakeel.core.kg_models import RawExtraction
from datakeel.core.kg_product import ProductExtraction
from datakeel.core.models import AssetRef
from datakeel.transcription.alignment import align_regions


def _quotes(draft: ObservationDraft, document: KGDocument) -> tuple[str, ...]:
    detail = draft.verification_detail
    if detail is None:
        return ()
    spans = (detail.head,) if draft.predicate == "kg.mentions" else (detail.evidence,)
    return tuple(document.text[span.start : span.end] for span in spans if span is not None)


def _image_draft(
    draft: ObservationDraft, document: KGDocument, person_ids: set[str], quotes: tuple[str, ...]
) -> ObservationDraft:
    image = document.image
    if image is None:
        return draft
    regions: tuple[ImageRegion, ...] = tuple(
        dict.fromkeys(
            region
            for quote in quotes
            for region in align_regions(quote, image.lines, image.width, image.height)
        )
    )
    issues: list[VerificationIssue] = []
    if not regions:
        issues.append(VerificationIssue(code="image_unlocated"))
    if draft.subject.asset_id in person_ids or (
        isinstance(draft.object, AssetRef) and draft.object.asset_id in person_ids
    ):
        issues.append(VerificationIssue(code="handwriting_name"))
    detail = draft.verification_detail or VerificationDetail()
    detail = detail.model_copy(
        update={
            "issues": tuple(dict.fromkeys((*detail.issues, *issues))),
            "locations": tuple(
                location.model_copy(
                    update={"issues": tuple(dict.fromkeys((*location.issues, *issues)))}
                )
                for location in detail.locations
            ),
        }
    )
    anchors = tuple(
        EvidenceAnchor(
            asset_ref=image.asset_ref, content_revision=image.content_revision, selector=region
        )
        for region in regions or (Whole(),)
    )
    return draft.model_copy(
        update={
            "anchors": (*draft.anchors, *anchors),
            "verification_detail": detail,
            "verification": "needs_review" if detail.issues else "verified",
        }
    )


def enrich_image_product(
    product: ProductExtraction,
    document: KGDocument,
    schema: KGSchema,
    *,
    handwriting: bool = False,
    raw: RawExtraction | None = None,
) -> ProductExtraction:
    """Keep text checks intact and add OCR-only image locations plus handwriting cautions."""
    if document.image is None:
        return product
    people: set[str] = (
        {item.name for item in schema.entity_types if item.person} if handwriting else set()
    )
    person_ids = {entity.asset_ref.asset_id for entity in product.entities if entity.type in people}
    names = {entity.asset_ref.asset_id: entity.name for entity in product.entities}
    drafts: list[ObservationDraft] = []
    for draft in product.drafts:
        quotes = _quotes(draft, document)
        if raw is not None and isinstance(draft.object, AssetRef):
            supplied = tuple(
                relation.evidence
                for relation in raw.relations
                if f"kg.{relation.relation}" == draft.predicate
                and relation.head == names.get(draft.subject.asset_id)
                and relation.tail == names.get(draft.object.asset_id)
            )
            quotes = supplied or quotes
        drafts.append(_image_draft(draft, document, person_ids, quotes))
    return product.model_copy(update={"drafts": tuple(drafts)})
