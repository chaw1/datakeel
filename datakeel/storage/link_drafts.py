# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Assemble exact, source-anchored association observations for latest graph versions."""

import hashlib

from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot
from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_models import EvidenceAnchor, ExtractorRef, TextSpan
from datakeel.core.kg_product import KGEntity
from datakeel.core.link_matching import match_entity
from datakeel.core.link_models import LinkGraph, LinkMetadata
from datakeel.core.models import AssetRef
from datakeel.storage.link_reviews import LinkReview


def target_reference(target: CatalogObject) -> AssetRef:
    """Use semantic card versions and stable table/view projection revisions."""
    return target.asset_ref.model_copy(
        update={
            "version": target.asset_ref.version
            if target.asset_ref.asset_type == "metric"
            else str(target.revision)
        }
    )


def link_identity(draft: ObservationDraft) -> str:
    """Bind both endpoint revisions, mention evidence and match cardinality to identity."""
    return "link-" + hashlib.sha256(draft.model_dump_json().encode()).hexdigest()


def _anchors(entity: KGEntity, graph: LinkGraph) -> tuple[EvidenceAnchor, ...]:
    anchors = {
        anchor.model_dump_json(): anchor
        for assertion in graph.assertions
        if assertion.predicate == "kg.mentions" and assertion.subject == entity.asset_ref
        for anchor in assertion.anchors
    }
    return tuple(anchors[key] for key in sorted(anchors))


def _mention_text(anchors: tuple[EvidenceAnchor, ...], graph: LinkGraph) -> tuple[str, ...]:
    documents = {
        (item.asset_ref.asset_id, item.asset_ref.version, item.content_revision): item.text
        for item in graph.documents
    }
    return tuple(
        text[anchor.selector.start : anchor.selector.end]
        for anchor in anchors
        if isinstance(anchor.selector, TextSpan)
        and (
            text := documents.get(
                (anchor.asset_ref.asset_id, anchor.asset_ref.version, anchor.content_revision)
            )
        )
        is not None
    )


def _draft(
    entity: KGEntity,
    target: CatalogObject,
    anchors: tuple[EvidenceAnchor, ...],
    metadata: LinkMetadata,
) -> ObservationDraft:
    return ObservationDraft(
        subject=entity.asset_ref,
        predicate="link.maps_to",
        object=target_reference(target),
        anchors=anchors,
        extractor=ExtractorRef(id="evidence.kg_link", version="1.0"),
        reason=metadata.model_dump_json(),
        verification="verified",
    )


def _entity_drafts(
    entity: KGEntity,
    graph: LinkGraph,
    catalog: CatalogSnapshot,
    reviews: tuple[LinkReview, ...],
) -> tuple[ObservationDraft, ...]:
    anchors = _anchors(entity, graph)
    if not anchors:
        return ()
    matches = match_entity(entity, _mention_text(anchors, graph), catalog)
    drafts = {
        match.target.asset_ref.asset_id: _draft(
            entity,
            match.target,
            anchors,
            LinkMetadata(
                match_kind="unique" if len(matches) == 1 else "ambiguous", basis=match.basis
            ),
        )
        for match in matches
    }
    targets = {item.asset_ref.asset_id: item for item in catalog.objects}
    for review in reviews:
        previous = review.assertion
        if (
            review.decision.status != "candidate"
            and previous.subject.asset_id == entity.asset_ref.asset_id
            and isinstance(previous.object, AssetRef)
            and previous.object.asset_id in targets
            and previous.object.asset_id not in drafts
        ):
            drafts[previous.object.asset_id] = _draft(
                entity,
                targets[previous.object.asset_id],
                anchors,
                LinkMetadata.model_validate_json(previous.reason or "{}"),
            )
    return tuple(drafts[key] for key in sorted(drafts))


def link_drafts(
    graphs: tuple[LinkGraph, ...], catalog: CatalogSnapshot, reviews: tuple[LinkReview, ...]
) -> tuple[ObservationDraft, ...]:
    """Retain reviewed associations while recomputing all deterministic candidates."""
    return tuple(
        draft
        for graph in graphs
        for entity in graph.entities
        if entity.type in {"dataset", "metric"}
        for draft in _entity_drafts(entity, graph, catalog, reviews)
    )
