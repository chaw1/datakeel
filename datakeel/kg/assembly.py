# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Turn filtered raw graph claims into ordinary candidate evidence drafts."""

from collections import defaultdict

from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_models import (
    EvidenceAnchor,
    TextSpan,
    VerificationDetail,
    VerificationIssue,
    VerificationLocation,
    Whole,
)
from datakeel.core.kg_contracts import ExtractedEntity, ExtractedRelation, KGSchema
from datakeel.core.kg_models import RawExtraction
from datakeel.core.kg_product import KGEntity, KGSource, ProductExtraction, SchemaProposal
from datakeel.core.kg_registry import register_kg_schema
from datakeel.kg.endpoints import ResolvedEndpoints, resolve_endpoints
from datakeel.kg.identity import entity_asset_ref, merge_drafts
from datakeel.kg.text import normalize_name
from datakeel.kg.verification import entity_spans, find_spans, nearest_span


def _spellings(entity: ExtractedEntity, schema: KGSchema) -> tuple[str, ...]:
    names = [entity.name]
    definition = next(item for item in schema.entity_types if item.name == entity.type)
    for canonical, aliases in definition.aliases.items():
        group = (canonical, *aliases)
        if normalize_name(entity.name) in {normalize_name(name) for name in group}:
            names.extend(group)
    return tuple(dict.fromkeys(names))


def _anchor(source: KGSource, span: TextSpan | None) -> EvidenceAnchor:
    return EvidenceAnchor(
        asset_ref=source.file,
        content_revision=source.content_revision,
        selector=span or Whole(),
    )


def _mention_drafts(
    entity: ExtractedEntity, schema: KGSchema, source: KGSource
) -> tuple[ObservationDraft, ...]:
    spans = entity_spans(source.text, _spellings(entity, schema))
    return tuple(
        ObservationDraft(
            subject=entity_asset_ref(source.dataset_id, source.dataset_version_id, entity),
            predicate="kg.mentions",
            object=source.file,
            anchors=(_anchor(source, span),),
            extractor=source.extractor,
            verification="verified" if span else "needs_review",
            verification_detail=VerificationDetail(
                head=span,
                issues=() if span else (VerificationIssue(code="head", role="head"),),
                locations=(
                    VerificationLocation(
                        source=source.file,
                        head=span,
                        issues=() if span else (VerificationIssue(code="head", role="head"),),
                    ),
                ),
            ),
        )
        for span in spans or (None,)
    )


def _relation_draft(
    relation: ExtractedRelation, resolved: ResolvedEndpoints, schema: KGSchema, source: KGSource
) -> ObservationDraft:
    if resolved.head is None or resolved.tail is None:
        msg = "Resolved endpoints are required for relation assembly"
        raise ValueError(msg)
    matches = find_spans(source.text, relation.evidence)
    inside = tuple(
        span
        for span in matches
        if span.start >= source.block_start and span.end <= (source.block_end or len(source.text))
    )
    evidence = nearest_span(
        inside or matches, TextSpan(start=source.block_start, end=source.block_start + 1)
    )
    head = nearest_span(entity_spans(source.text, _spellings(resolved.head, schema)), evidence)
    tail = nearest_span(entity_spans(source.text, _spellings(resolved.tail, schema)), evidence)
    issues: list[VerificationIssue] = []
    if evidence is None:
        issues.append(VerificationIssue(code="evidence"))
    if head is None:
        issues.append(VerificationIssue(code="head", role="head"))
    if tail is None:
        issues.append(VerificationIssue(code="tail", role="tail"))
    issues.extend(
        VerificationIssue(code="endpoint_undeclared", role=role) for role in resolved.undeclared
    )
    anchors = [_anchor(source, evidence)]
    anchors.extend(_anchor(source, span) for span in (head, tail) if span is not None)
    return ObservationDraft(
        subject=entity_asset_ref(source.dataset_id, source.dataset_version_id, resolved.head),
        predicate=f"kg.{relation.relation}",
        object=entity_asset_ref(source.dataset_id, source.dataset_version_id, resolved.tail),
        anchors=tuple(dict.fromkeys(anchors)),
        extractor=source.extractor,
        verification="needs_review" if issues else "verified",
        verification_detail=VerificationDetail(
            issues=tuple(issues),
            evidence=evidence,
            head=head,
            tail=tail,
            locations=(
                VerificationLocation(
                    source=source.file,
                    evidence=evidence,
                    head=head,
                    tail=tail,
                    issues=tuple(issues),
                ),
            ),
        ),
    )


def _normalized_entities(raw: RawExtraction, schema: KGSchema) -> tuple[ExtractedEntity, ...]:
    types = {item.name.casefold(): item.name for item in schema.entity_types}
    return tuple(
        entity.model_copy(
            update={
                "type": types.get(entity.type.strip().casefold(), entity.type.strip().casefold())
            }
        )
        if entity.type.strip()
        else entity
        for entity in raw.entities
    )


def _proposals(
    relations: dict[str, list[ExtractedRelation]], unknown: tuple[ExtractedEntity, ...]
) -> tuple[SchemaProposal, ...]:
    if unknown:
        relations.setdefault("unknown_entity_type", [])
    return tuple(
        SchemaProposal.model_validate(
            {
                "reason": reason,
                "count": len(items) + (len(unknown) if reason == "unknown_entity_type" else 0),
                "samples": items[:20],
                "entity_samples": unknown[:20] if reason == "unknown_entity_type" else (),
            }
        )
        for reason, items in sorted(relations.items())
    )


def assemble_extraction(
    raw: RawExtraction, schema: KGSchema, source: KGSource
) -> ProductExtraction:
    """Preserve unverified candidates and report every schema-excluded relation."""
    register_kg_schema(schema)
    types = {item.name for item in schema.entity_types}
    normalized = _normalized_entities(raw, schema)
    unknown = tuple(entity for entity in normalized if entity.type not in types)
    entities = {
        (entity.type, normalize_name(entity.name)): entity
        for entity in normalized
        if entity.type in types
    }
    drafts: list[ObservationDraft] = []
    proposals: dict[str, list[ExtractedRelation]] = defaultdict(list)
    definitions = {item.name: item for item in schema.relations}
    for relation in raw.relations:
        definition = definitions.get(relation.relation)
        if definition is None:
            proposals["unknown_relation"].append(relation)
            continue
        resolved = resolve_endpoints(relation, definition, normalized)
        if any(
            entity is not None and entity.type not in types
            for entity in (resolved.head, resolved.tail)
        ):
            proposals["unknown_entity_type"].append(relation)
            continue
        if resolved.reason:
            proposals[resolved.reason].append(relation)
            continue
        if resolved.head is not None and resolved.tail is not None:
            for entity in (resolved.head, resolved.tail):
                entities[(entity.type, normalize_name(entity.name))] = entity
        drafts.append(_relation_draft(relation, resolved, schema, source))
    ordered = [entities[key] for key in sorted(entities)]
    for entity in ordered:
        drafts.extend(_mention_drafts(entity, schema, source))
    return ProductExtraction(
        entities=tuple(
            KGEntity(
                asset_ref=entity_asset_ref(source.dataset_id, source.dataset_version_id, entity),
                name=entity.name,
                type=entity.type,
            )
            for entity in ordered
        ),
        drafts=merge_drafts(tuple(drafts)),
        proposals=_proposals(proposals, unknown),
    )
