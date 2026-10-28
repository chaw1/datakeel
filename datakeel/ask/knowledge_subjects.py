# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Find longest nonoverlapping registered subjects before interpreting relationship language."""

from difflib import SequenceMatcher

from datakeel.ask.knowledge_names import (
    SubjectMention,
    SubjectName,
    name_occurrences,
    name_variants,
    normalize_name,
)
from datakeel.ask.matching import metric_matches
from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot, TableProperties
from datakeel.core.evidence_models import TextSpan
from datakeel.core.kg_product import KGEntity
from datakeel.core.knowledge_models import KnowledgeSubject
from datakeel.core.link_matching import catalog_names
from datakeel.core.link_models import EntityLink, LinkContext, LinkEntitySource
from datakeel.core.metric_models import SemanticLayer


def catalog_subject(item: CatalogObject) -> KnowledgeSubject:
    """Convert supported catalog identities into the public subject contract."""
    kind = item.asset_ref.asset_type
    if kind == "table" and TableProperties.model_validate(item.properties.root).is_view:
        kind = "view"
    return KnowledgeSubject(
        asset_ref=item.asset_ref.model_copy(update={"version": str(item.revision)})
        if item.asset_ref.version is None
        else item.asset_ref,
        name=item.name,
        kind="metric"
        if kind == "metric"
        else "owner"
        if kind == "owner"
        else "view"
        if kind == "view"
        else "table",
    )


def entity_subject(entity: KGEntity, source: LinkEntitySource | None = None) -> KnowledgeSubject:
    """Retain graph identity, type and dataset for document subjects."""
    return KnowledgeSubject(
        asset_ref=entity.asset_ref,
        name=entity.name,
        kind="kg_entity",
        entity_type=entity.type,
        dataset_id=source.dataset_id if source else None,
        dataset_name=source.dataset_name if source else None,
    )


def _metric_names(catalog: CatalogSnapshot, layer: SemanticLayer) -> list[SubjectName]:
    targets = {
        item.asset_ref.asset_id: catalog_subject(item)
        for item in catalog.objects
        if item.asset_ref.asset_type == "metric"
    }
    names: list[SubjectName] = []
    for metric in layer.metrics:
        if metric.id not in targets:
            continue
        names.extend(
            SubjectName(name=value, subject=targets[metric.id], rank=rank)
            for rank, values in (
                (2, (metric.name, metric.english_name)),
                (2, metric.synonyms),
                (0, (metric.id,)),
            )
            for value in values
            if value
        )
        for term in layer.terms:
            if (term.means.kind == "metric" and term.means.id == metric.id) or (
                term.means.kind == "column" and term.means.id == metric.measure.column
            ):
                names.extend(
                    SubjectName(name=value, subject=targets[metric.id], rank=2)
                    for value in (term.term, *term.synonyms)
                )
    return names


def _graph_names(context: LinkContext) -> list[SubjectName]:
    sources = {item.entity_id: item for item in context.entity_sources}
    entities = {item.asset_ref: item for item in context.entities}
    names = [
        SubjectName(
            name=item.name, subject=entity_subject(item, sources.get(item.asset_ref.asset_id))
        )
        for item in context.entities
    ]
    documents = {(doc.asset_ref, doc.content_revision): doc.text for doc in context.documents}
    for assertion in context.assertions:
        if assertion.predicate != "kg.mentions" or assertion.status == "rejected":
            continue
        entity = entities.get(assertion.subject)
        if entity is None:
            continue
        for anchor in assertion.anchors:
            text = documents.get((anchor.asset_ref, anchor.content_revision))
            if text is not None and isinstance(anchor.selector, TextSpan):
                names.append(
                    SubjectName(
                        name=text[anchor.selector.start : anchor.selector.end],
                        subject=entity_subject(entity, sources.get(entity.asset_ref.asset_id)),
                    )
                )
    return names


def _vocabulary(
    catalog: CatalogSnapshot, layer: SemanticLayer, context: LinkContext
) -> tuple[SubjectName, ...]:
    names = _metric_names(catalog, layer)
    for item in catalog.objects:
        if item.asset_ref.asset_type not in {"table", "owner"}:
            continue
        subject = catalog_subject(item)
        values = catalog_names(item) if subject.kind in {"table", "view"} else (item.name,)
        for value in values:
            names.append(SubjectName(name=value, subject=subject))
            if subject.kind in {"table", "view"}:
                names.extend(
                    SubjectName(name=value + suffix, subject=subject) for suffix in (" table", "表")
                )
    return (*names, *_graph_names(context))


def _collapsed(
    names: list[SubjectName], links: tuple[EntityLink, ...]
) -> tuple[KnowledgeSubject, ...]:
    strongest = max((item.rank for item in names), default=0)
    candidates = tuple(
        {
            item.subject.asset_ref: item.subject
            for item in names
            if item.subject.kind != "metric" or item.rank == strongest
        }.values()
    )
    assets = {item.asset_ref.asset_id for item in candidates if item.kind != "kg_entity"}
    roles = {normalize_name(item.name) for item in candidates if item.kind == "owner"}
    return tuple(
        item
        for item in candidates
        if not (
            item.kind == "kg_entity"
            and (
                (
                    item.entity_type in {"person", "organization"}
                    and normalize_name(item.name) in roles
                )
                or any(
                    link.entity.asset_ref == item.asset_ref
                    and link.target.asset_ref.asset_id in assets
                    and link.assertion.status != "rejected"
                    for link in links
                )
            )
        )
    )


def subject_mentions(
    question: str, catalog: CatalogSnapshot, layer: SemanticLayer, context: LinkContext
) -> tuple[SubjectMention, ...]:
    """Choose longest spans across every vocabulary, retaining equal-span identity ambiguity."""
    text = normalize_name(question)
    spans: dict[tuple[int, int], list[SubjectName]] = {}
    for item in _vocabulary(catalog, layer, context):
        for name in name_variants(item.name):
            for span in name_occurrences(text, name):
                spans.setdefault(span, []).append(item)
    targets = {
        item.asset_ref.asset_id: catalog_subject(item)
        for item in catalog.objects
        if item.asset_ref.asset_type == "metric"
    }
    for match in metric_matches(text, layer):
        if match.match_kind == "normalized" and match.metric_id in targets:
            spans.setdefault((match.start, match.end), []).append(
                SubjectName(name=match.text, subject=targets[match.metric_id], rank=0)
            )
    selected: list[SubjectMention] = []
    for (start, end), names in sorted(
        spans.items(), key=lambda item: (item[0][0] - item[0][1], item[0][0])
    ):
        if any(start < item.end and end > item.start for item in selected):
            continue
        selected.append(
            SubjectMention(
                start=start,
                end=end,
                text=text[start:end],
                candidates=_collapsed(names, context.links),
            )
        )
    return tuple(sorted(selected, key=lambda item: item.start))


def subject_candidates(
    text: str,
    catalog: CatalogSnapshot,
    layer: SemanticLayer,
    entities: tuple[KGEntity, ...],
    *,
    links: tuple[EntityLink, ...] = (),
    entity_sources: tuple[LinkEntitySource, ...] = (),
) -> tuple[KnowledgeSubject, ...]:
    """Expose the same subject-first match used by the production question route."""
    mentions = subject_mentions(
        text,
        catalog,
        layer,
        LinkContext(entities=entities, links=links, entity_sources=entity_sources),
    )
    return tuple(
        {item.asset_ref: item for mention in mentions for item in mention.candidates}.values()
    )


def subject_suggestions(
    text: str,
    catalog: CatalogSnapshot,
    entities: tuple[KGEntity, ...],
    *,
    entity_sources: tuple[LinkEntitySource, ...] = (),
) -> tuple[KnowledgeSubject, ...]:
    """Use similarity only for bounded suggestions after exact subject matching failed."""
    candidates = [
        catalog_subject(item)
        for item in catalog.objects
        if item.asset_ref.asset_type in {"metric", "table"}
    ]
    sources = {item.entity_id: item for item in entity_sources}
    candidates.extend(
        entity_subject(item, sources.get(item.asset_ref.asset_id)) for item in entities
    )
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                -max(
                    SequenceMatcher(None, normalize_name(text), normalize_name(label)).ratio()
                    for label in (item.name, item.asset_ref.asset_id)
                ),
                item.asset_ref.asset_id,
            ),
        )[:3]
    )
