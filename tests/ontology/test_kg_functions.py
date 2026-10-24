# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep graph functions available to both Agent and MCP through the common registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.kg_queries import KGQueryResult, KGRelationExplanation
from datakeel.core.models import JsonDocument
from datakeel.ontology.functions import invoke_function
from tests.kg.helpers import graph_product, seed_graph

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_graph_functions_return_missing_checks_and_source_refs(db: Database) -> None:
    """The read envelope carries explicit entity and document provenance."""
    product, source = graph_product(missing=True)
    assertions = seed_graph(db, product, source)
    relation = next(item for item in assertions if item.predicate == "kg.uses")
    result = invoke_function(db, "query_kg", JsonDocument({"verification": "needs_review"}))
    assert KGQueryResult.model_validate(result.data).relations
    explanation = invoke_function(
        db, "explain_relation", JsonDocument({"assertion_id": relation.id})
    )
    assert "tail entity" in KGRelationExplanation.model_validate(explanation.data).summary
    assert {ref.asset_type for ref in explanation.asset_refs} == {"kg_entity", "file"}
    empty = invoke_function(db, "query_kg", JsonDocument({"dataset_id": "absent"}))
    assert empty.asset_refs[0].asset_id == "absent"
    assert (
        invoke_function(db, "query_kg", JsonDocument({"name": "absent"})).asset_refs[0].asset_type
        == "dataset"
    )
