# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve whole subjects across vocabularies before scanning individual catalog tiers."""

import unicodedata
from difflib import SequenceMatcher

from datakeel.ask.matching import metric_matches, occurrences
from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot, TableProperties
from datakeel.core.catalog_vocabulary import catalog_identifiers, normalized_subject_name
from datakeel.core.kg_product import KGEntity
from datakeel.core.knowledge_models import KnowledgeSubject
from datakeel.core.link_matching import catalog_names
from datakeel.core.link_models import EntityLink, LinkEntitySource
from datakeel.core.metric_models import SemanticLayer


def normalized_name(text: str) -> str:
    """Apply graph identity normalization without fuzzy or substring comparisons."""
    return " ".join(unicodedata.normalize("NFKC", text).strip().lower().split())


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
    """Retain graph identity and type for an entity outside the registered catalog."""
    return KnowledgeSubject(
        asset_ref=entity.asset_ref,
        name=entity.name,
        kind="kg_entity",
        entity_type=entity.type,
        dataset_id=source.dataset_id if source else None,
        dataset_name=source.dataset_name if source else None,
    )


def subject_candidates(
    text: str,
    catalog: CatalogSnapshot,
    layer: SemanticLayer,
    entities: tuple[KGEntity, ...],
    *,
    links: tuple[EntityLink, ...] = (),
    entity_sources: tuple[LinkEntitySource, ...] = (),
) -> tuple[KnowledgeSubject, ...]:
    """Prefer complete names across tiers and preserve genuinely distinct graph candidates."""
    name = normalized_subject_name(text)
    if not name:
        return ()
    metrics = _metric_candidates(name, catalog, layer, exact=True)
    named = _named_candidates(name, catalog, exact=True)
    sources = {item.entity_id: item for item in entity_sources}
    graph = tuple(
        entity_subject(entity, sources.get(entity.asset_ref.asset_id))
        for entity in entities
        if normalized_subject_name(entity.name) == name
        and not _linked_to(entity, (*metrics, *named), links)
    )
    if metrics or named or graph:
        return (*metrics, *named, *graph)
    return _metric_candidates(name, catalog, layer, exact=False) or _named_candidates(
        name, catalog, exact=False
    )


def _linked_to(
    entity: KGEntity, subjects: tuple[KnowledgeSubject, ...], links: tuple[EntityLink, ...]
) -> bool:
    return any(
        link.entity.asset_ref == entity.asset_ref
        and link.target.asset_ref.asset_id in {item.asset_ref.asset_id for item in subjects}
        and link.assertion.status != "rejected"
        for link in links
    )


def _metric_candidates(
    text: str, catalog: CatalogSnapshot, layer: SemanticLayer, *, exact: bool
) -> tuple[KnowledgeSubject, ...]:
    ranks = {"exact": 3, "synonym": 2, "prefix": 1}
    scores = _exact_metric_scores(text, layer)
    for match in () if exact else metric_matches(text, layer):
        if match.metric_id:
            scores[match.metric_id] = max(scores.get(match.metric_id, 0), ranks[match.match_kind])
    for metric in () if exact else layer.metrics:
        if occurrences(text, metric.id):
            scores[metric.id] = 3
    strongest = max(scores.values(), default=0)
    return tuple(
        catalog_subject(item)
        for item in catalog.objects
        if item.asset_ref.asset_type == "metric"
        and scores.get(item.asset_ref.asset_id) == strongest
    )


def _exact_metric_scores(text: str, layer: SemanticLayer) -> dict[str, int]:
    scores: dict[str, int] = {}
    for metric in layer.metrics:
        if text in {normalized_subject_name(value) for value in (metric.name, metric.id)}:
            scores[metric.id] = 3
        elif text in {normalized_subject_name(value) for value in metric.synonyms}:
            scores[metric.id] = 2
    for term in layer.terms:
        rank = (
            3
            if normalized_subject_name(term.term) == text
            else 2
            if text in {normalized_subject_name(value) for value in term.synonyms}
            else 0
        )
        for metric in layer.metrics:
            if rank and (
                (term.means.kind == "metric" and term.means.id == metric.id)
                or (term.means.kind == "column" and term.means.id == metric.measure.column)
            ):
                scores[metric.id] = max(scores.get(metric.id, 0), rank)
    return scores


def _named_candidates(
    text: str, catalog: CatalogSnapshot, *, exact: bool
) -> tuple[KnowledgeSubject, ...]:
    identifiers = set(catalog_identifiers(text))
    return tuple(
        catalog_subject(item)
        for item in catalog.objects
        if (
            item.asset_ref.asset_type == "table"
            and (
                text in {normalized_subject_name(name) for name in catalog_names(item)}
                if exact
                else identifiers.intersection(catalog_names(item))
            )
        )
        or (item.asset_ref.asset_type == "owner" and text == normalized_subject_name(item.name))
    )


def subject_suggestions(
    text: str,
    catalog: CatalogSnapshot,
    entities: tuple[KGEntity, ...],
    *,
    entity_sources: tuple[LinkEntitySource, ...] = (),
) -> tuple[KnowledgeSubject, ...]:
    """Use similarity only for at most three suggestions after exact resolution failed."""
    candidates = [
        catalog_subject(item)
        for item in catalog.objects
        if item.asset_ref.asset_type in {"metric", "table"}
    ]
    sources = {item.entity_id: item for item in entity_sources}
    candidates.extend(
        entity_subject(entity, sources.get(entity.asset_ref.asset_id)) for entity in entities
    )
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                -max(
                    SequenceMatcher(None, normalized_name(text), normalized_name(label)).ratio()
                    for label in (item.name, item.asset_ref.asset_id)
                ),
                item.asset_ref.asset_id,
            ),
        )[:3]
    )
