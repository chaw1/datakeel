# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve knowledge subjects by deterministic, short-circuiting vocabulary tiers."""

import re
import unicodedata
from difflib import SequenceMatcher

from datakeel.ask.matching import metric_matches, occurrences
from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot, TableProperties
from datakeel.core.kg_product import KGEntity
from datakeel.core.knowledge_models import KnowledgeSubject
from datakeel.core.metric_models import SemanticLayer

_IDENTIFIERS = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:[./][A-Za-z][A-Za-z0-9_]*)*")
_STOP = {"table", "tables", "the", "表"}


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


def entity_subject(entity: KGEntity) -> KnowledgeSubject:
    """Retain graph identity and type for an entity outside the registered catalog."""
    return KnowledgeSubject(
        asset_ref=entity.asset_ref, name=entity.name, kind="kg_entity", entity_type=entity.type
    )


def subject_candidates(
    text: str, catalog: CatalogSnapshot, layer: SemanticLayer, entities: tuple[KGEntity, ...]
) -> tuple[KnowledgeSubject, ...]:
    """Stop at the first matching tier: metrics, catalog or roles, then graph entities."""
    ranks = {"exact": 3, "synonym": 2, "prefix": 1}
    scores: dict[str, int] = {}
    for match in metric_matches(text, layer):
        if match.metric_id:
            scores[match.metric_id] = max(scores.get(match.metric_id, 0), ranks[match.match_kind])
    for metric in layer.metrics:
        if occurrences(text, metric.id):
            scores[metric.id] = 3
    if scores:
        strongest = max(scores.values())
        return tuple(
            catalog_subject(item)
            for item in catalog.objects
            if item.asset_ref.asset_type == "metric"
            and scores.get(item.asset_ref.asset_id) == strongest
        )
    identifiers = {value.lower() for value in _IDENTIFIERS.findall(text)} - _STOP
    named = tuple(
        catalog_subject(item)
        for item in catalog.objects
        if (
            item.asset_ref.asset_type == "table"
            and identifiers.intersection(
                {
                    item.name.lower(),
                    f"{item.schema_name}.{item.name}".lower(),
                    item.asset_ref.asset_id.lower(),
                }
            )
        )
        or (
            item.asset_ref.asset_type == "owner"
            and normalized_name(text) == normalized_name(item.name)
        )
    )
    if named:
        return named
    return tuple(
        entity_subject(entity)
        for entity in entities
        if normalized_name(entity.name) == normalized_name(text)
    )


def subject_suggestions(
    text: str, catalog: CatalogSnapshot, entities: tuple[KGEntity, ...]
) -> tuple[KnowledgeSubject, ...]:
    """Use similarity only for at most three suggestions after exact resolution failed."""
    candidates = [
        catalog_subject(item)
        for item in catalog.objects
        if item.asset_ref.asset_type in {"metric", "table"}
    ]
    candidates.extend(entity_subject(entity) for entity in entities)
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
