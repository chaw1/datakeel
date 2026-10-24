# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Project accepted alias pairs with explicit rejected-pair separation constraints."""

from datakeel.core.evidence_models import Assertion
from datakeel.core.kg_product import KGEntity
from datakeel.core.kg_queries import KGGraph, KGGraphEdge, KGGraphNode, KGQueryResult
from datakeel.core.models import AssetRef


def _groups(
    entities: dict[str, KGEntity], assertions: tuple[Assertion, ...]
) -> dict[str, set[str]]:
    pairs = tuple(
        assertion
        for assertion in assertions
        if assertion.predicate == "kg.same_as"
        and isinstance(assertion.object, AssetRef)
        and assertion.subject.asset_id in entities
        and assertion.object.asset_id in entities
    )
    rejected = {
        frozenset((pair.subject.asset_id, pair.object.asset_id))
        for pair in pairs
        if pair.status == "rejected" and isinstance(pair.object, AssetRef)
    }
    groups = {key: {key} for key in entities}
    for pair in sorted(pairs, key=lambda item: item.id):
        if pair.status != "accepted" or not isinstance(pair.object, AssetRef):
            continue
        left, right = groups[pair.subject.asset_id], groups[pair.object.asset_id]
        combined = left | right
        if any(rejection <= combined for rejection in rejected):
            continue
        for key in combined:
            groups[key] = combined
    return groups


def project_graph(
    result: KGQueryResult,
    entities: tuple[KGEntity, ...],
    assertions: tuple[Assertion, ...],
    limit: int,
) -> KGGraph:
    """Bound visible nodes and edges without generating transitive same-as assertions."""
    by_id = {entity.asset_ref.asset_id: entity for entity in entities}
    groups = _groups(by_id, assertions)
    selected = tuple(
        dict.fromkeys(
            [
                entity.asset_ref.asset_id
                for relation in result.relations
                for entity in (relation.head, relation.tail)
            ]
            + [entity.asset_ref.asset_id for entity in result.entities]
        )
    )
    representatives = tuple(dict.fromkeys(min(groups[key]) for key in selected))
    chosen = representatives[:limit]
    nodes = tuple(
        KGGraphNode(
            id=key,
            label=" / ".join(by_id[member].name for member in sorted(groups[key])),
            entity_type=by_id[key].type,
            members=tuple(sorted(groups[key])),
        )
        for key in chosen
    )
    edges: list[KGGraphEdge] = []
    for relation in result.relations:
        source, target = (
            min(groups[entity.asset_ref.asset_id]) for entity in (relation.head, relation.tail)
        )
        if source not in chosen or target not in chosen:
            continue
        if source == target and relation.assertion.predicate == "kg.same_as":
            continue
        edges.append(
            KGGraphEdge(
                id=relation.assertion.id,
                source=source,
                target=target,
                predicate=relation.assertion.predicate,
                status=relation.assertion.status,
                verification=relation.assertion.verification,
            )
        )
    return KGGraph(
        dataset_id=result.dataset_id,
        version_id=result.version_id,
        nodes=nodes,
        edges=tuple(edges[:limit]),
        truncated=result.truncated or len(representatives) > limit or len(edges) > limit,
    )
