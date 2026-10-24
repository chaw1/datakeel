# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve model endpoint spellings without guessing ambiguous missing types."""

from typing import Literal

from datakeel.core.kg_contracts import ExtractedEntity, ExtractedRelation, RelationType
from datakeel.core.models import BoundaryModel
from datakeel.kg.text import normalize_name


class ResolvedEndpoints(BoundaryModel):
    """Keep resolved entities and explicitly synthesized endpoint roles together."""

    head: ExtractedEntity | None = None
    tail: ExtractedEntity | None = None
    undeclared: tuple[Literal["head", "tail"], ...] = ()
    reason: Literal["domain_range", "endpoint_ambiguous"] | None = None


def _resolve(
    name: str, entities: tuple[ExtractedEntity, ...], allowed: tuple[str, ...]
) -> tuple[ExtractedEntity | None, bool]:
    normalized = normalize_name(name)
    exact = [entity for entity in entities if normalize_name(entity.name) == normalized]
    containing = [
        entity
        for entity in entities
        if normalized in normalize_name(entity.name) or normalize_name(entity.name) in normalized
    ]
    matches = exact or containing
    if matches:
        permitted = [entity for entity in matches if entity.type in allowed]
        return min(permitted or matches, key=lambda entity: (-len(entity.name), entity.name)), False
    if len(allowed) == 1:
        return ExtractedEntity(name=name, type=allowed[0]), True
    return None, True


def resolve_endpoints(
    relation: ExtractedRelation, definition: RelationType, entities: tuple[ExtractedEntity, ...]
) -> ResolvedEndpoints:
    """Use declarations first and synthesize only uniquely determined missing types."""
    head, head_new = _resolve(relation.head, entities, definition.domain)
    tail, tail_new = _resolve(relation.tail, entities, definition.range)
    if head is None or tail is None:
        return ResolvedEndpoints(reason="endpoint_ambiguous")
    if head.type not in definition.domain or tail.type not in definition.range:
        return ResolvedEndpoints(reason="domain_range")
    roles: list[Literal["head", "tail"]] = []
    if head_new:
        roles.append("head")
    if tail_new:
        roles.append("tail")
    return ResolvedEndpoints(head=head, tail=tail, undeclared=tuple(roles))
