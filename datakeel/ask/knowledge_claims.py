# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Select directional document claims through non-rejected, unambiguous asset links."""

from collections.abc import Callable
from typing import Literal

from datakeel.core.evidence_models import Assertion, EvidenceAnchor, TextSpan
from datakeel.core.kg_product import KGEntity
from datakeel.core.kg_queries import KGSourceText
from datakeel.core.knowledge_models import (
    KnowledgeClaim,
    KnowledgeEvidence,
    KnowledgeIntent,
    KnowledgeOtherEnd,
    KnowledgeSubject,
    KnowledgeSubjectLink,
)
from datakeel.core.link_models import EntityLink, LinkContext
from datakeel.core.models import AssetRef

SourceReader = Callable[[EvidenceAnchor], KGSourceText]


def usable_link(link: EntityLink) -> bool:
    """Use accepted links and unique candidates, never rejected or ambiguous candidates."""
    return link.assertion.status == "accepted" or (
        link.assertion.status == "candidate" and link.match_kind == "unique"
    )


def document_claims(
    subject: KnowledgeSubject,
    intent: KnowledgeIntent,
    context: LinkContext,
    system_assets: set[str],
    source_reader: SourceReader,
) -> tuple[tuple[KnowledgeClaim, ...], int]:
    """Keep one-hop relation direction, review states, evidence and ambiguous counts explicit."""
    entities = {entity.asset_ref.asset_id: entity for entity in context.entities}
    selected: list[KnowledgeClaim] = []
    pending: set[str] = set()
    for assertion in context.assertions:
        if assertion.status == "rejected" or not isinstance(assertion.object, AssetRef):
            continue
        endpoint = _endpoint(assertion, intent)
        if (
            endpoint is None
            or assertion.subject.asset_id not in entities
            or assertion.object.asset_id not in entities
        ):
            continue
        direct = subject.kind == "kg_entity" and endpoint.asset_id == subject.asset_ref.asset_id
        link, ambiguous = _subject_path(endpoint, subject, context.links)
        if not direct and link is None:
            if ambiguous:
                pending.add(assertion.id)
            continue
        other = entities[
            assertion.object.asset_id
            if endpoint == assertion.subject
            else assertion.subject.asset_id
        ]
        other_end, ambiguous = _resolve_other_end(other, context.links)
        if other_end is None:
            if ambiguous:
                pending.add(assertion.id)
            continue
        selected.append(
            KnowledgeClaim(
                assertion_id=assertion.id,
                head=entities[assertion.subject.asset_id],
                predicate=assertion.predicate.removeprefix("kg."),
                tail=entities[assertion.object.asset_id],
                relation_status=assertion.status,
                verification=assertion.verification or "needs_review",
                evidence=_evidence(assertion, source_reader),
                subject_link=None if direct else _subject_link(link) if link else None,
                other_end=other_end,
                consistency=_consistency(other_end, intent, system_assets),
            )
        )
    return tuple(
        sorted(
            selected,
            key=lambda item: (item.predicate, item.head.name, item.tail.name, item.assertion_id),
        )
    ), len(pending)


def _subject_path(
    endpoint: AssetRef, subject: KnowledgeSubject, links: tuple[EntityLink, ...]
) -> tuple[EntityLink | None, bool]:
    matching = tuple(
        link
        for link in links
        if link.entity.asset_ref.asset_id == endpoint.asset_id
        and link.target.asset_ref.asset_id == subject.asset_ref.asset_id
    )
    selected = next((link for link in matching if usable_link(link)), None)
    ambiguous = any(
        link.assertion.status == "candidate" and link.match_kind == "ambiguous" for link in matching
    )
    return selected, ambiguous


def _resolve_other_end(
    other: KGEntity, links: tuple[EntityLink, ...]
) -> tuple[KnowledgeOtherEnd | None, bool]:
    matching = tuple(
        link
        for link in links
        if link.entity.asset_ref.asset_id == other.asset_ref.asset_id
        and link.assertion.status != "rejected"
    )
    selected = next((link for link in matching if usable_link(link)), None)
    if (
        other.type not in {"person", "organization", "location", "system"}
        and matching
        and selected is None
    ):
        return None, any(
            link.assertion.status == "candidate" and link.match_kind == "ambiguous"
            for link in matching
        )
    return _other_end(other, selected), False


def _endpoint(assertion: Assertion, intent: KnowledgeIntent) -> AssetRef | None:
    if not isinstance(assertion.object, AssetRef):
        return None
    relation = assertion.predicate
    if intent == "owner" and relation == "kg.owns":
        return assertion.object
    if intent == "owned" and relation == "kg.owns":
        return assertion.subject
    if relation in {"kg.derived_from", "kg.computed_from"}:
        if intent in {"upstream", "related"}:
            return assertion.subject
        if intent == "downstream":
            return assertion.object
    return assertion.object if intent == "related" and relation == "kg.owns" else None


def _subject_link(link: EntityLink) -> KnowledgeSubjectLink:
    return KnowledgeSubjectLink(
        entity=link.entity,
        asset_ref=link.target.asset_ref.model_copy(update={"version": str(link.target.revision)})
        if link.target.asset_ref.version is None
        else link.target.asset_ref,
        assertion_id=link.assertion.id,
        link_status="accepted" if link.assertion.status == "accepted" else "candidate",
    )


def _other_end(entity: KGEntity, link: EntityLink | None) -> KnowledgeOtherEnd:
    if entity.type in {"person", "organization", "location", "system"}:
        return KnowledgeOtherEnd(status="not_applicable", entity=entity)
    if link is None:
        return KnowledgeOtherEnd(status="not_in_catalog", entity=entity)
    resolved = _subject_link(link)
    return KnowledgeOtherEnd(
        status="linked",
        entity=entity,
        asset_ref=resolved.asset_ref,
        assertion_id=resolved.assertion_id,
        link_status=resolved.link_status,
    )


def _consistency(
    other: KnowledgeOtherEnd, intent: KnowledgeIntent, system_assets: set[str]
) -> Literal["consistent", "not_in_system", "not_in_catalog"] | None:
    if intent not in {"upstream", "downstream"}:
        return None
    if other.status == "not_in_catalog":
        return "not_in_catalog"
    if other.asset_ref is not None:
        return "consistent" if other.asset_ref.asset_id in system_assets else "not_in_system"
    return None


def _evidence(assertion: Assertion, source_reader: SourceReader) -> tuple[KnowledgeEvidence, ...]:
    evidence: list[KnowledgeEvidence] = []
    detail = assertion.verification_detail
    seen: set[AssetRef] = set()
    for anchor in assertion.anchors:
        if anchor.asset_ref in seen:
            continue
        seen.add(anchor.asset_ref)
        source = source_reader(anchor)
        location = (
            next((item for item in detail.locations if item.source == anchor.asset_ref), None)
            if detail
            else None
        )
        span = location.evidence if location else detail.evidence if detail else None
        if detail is None and isinstance(anchor.selector, TextSpan):
            span = anchor.selector
        evidence.append(
            KnowledgeEvidence(
                source=source.asset_ref,
                document=source.filename,
                text=source.text[span.start : span.end] if span else "",
                start=span.start if span else None,
                end=span.end if span else None,
            )
        )
    return tuple(evidence)
