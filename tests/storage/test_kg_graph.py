# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Display alias groups while treating rejected pairs as hard separation constraints."""

from datakeel.core.kg_product import ProductExtraction
from datakeel.core.kg_queries import KGEntityView, KGQueryResult, KGRelationView
from datakeel.kg.aliases import same_as_drafts
from datakeel.kg.loader import get_schema
from datakeel.storage.kg_graph import project_graph
from tests.kg.helpers import assertions_for, graph_product


def test_rejected_triangle_pair_cannot_remerge_through_an_accepted_path() -> None:
    """Accepted alias display groups cannot hide a rejected pair behind transitive closure."""
    products = [
        graph_product(name, f"file-{index}")
        for index, name in enumerate(("Acme", "Acme Group", "Acme Group East"))
    ]
    entities = tuple(
        entity
        for product, _ in products
        for entity in product.entities
        if entity.type == "organization"
    )
    drafts = tuple(draft for product, _ in products for draft in product.drafts)
    pairs = same_as_drafts(entities, drafts, get_schema(), products[0][1].extractor)
    accepted = tuple(
        assertion.model_copy(update={"status": "accepted"})
        for assertion in assertions_for(ProductExtraction(drafts=pairs))
    )
    views = tuple(KGEntityView(**entity.model_dump()) for entity in entities)
    by_id = {entity.asset_ref.asset_id: entity for entity in entities}
    relations = tuple(
        KGRelationView(
            assertion=assertion,
            head=by_id[assertion.subject.asset_id],
            tail=by_id[assertion.object.asset_id],
            extractor="fake",
            model="fake",
            extraction_id="run",
        )
        for assertion in accepted
    )
    result = KGQueryResult(entities=views, relations=relations)
    graph = project_graph(result, entities, accepted, 100)
    assert len(graph.nodes) == 1
    rejected = accepted[0].model_copy(update={"status": "rejected"})
    constrained = (rejected, *accepted[1:])
    graph = project_graph(result, entities, constrained, 100)
    assert len(graph.nodes) == 2
    assert not any(
        {rejected.subject.asset_id, rejected.object.asset_id} <= set(node.members)
        for node in graph.nodes
    )
    assert project_graph(result, entities, constrained[::-1], 100).nodes == graph.nodes
    assert len(accepted) == 3
    assert project_graph(result, entities, constrained, 1).truncated
