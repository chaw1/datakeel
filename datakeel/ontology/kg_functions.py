# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared Agent and MCP graph queries with typed original-source explanations."""

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.kg_queries import KGExplainQuery, KGQuery
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.ontology.models import FunctionResult
from datakeel.storage.database import Database
from datakeel.storage.kg_queries import explain_relation, query_kg


def invoke_kg(
    db: Database, name: str, arguments: JsonDocument, *, access: AccessContext | None = None
) -> FunctionResult:
    """Preserve graph and source asset identities in the ordinary read-tool envelope."""
    if name == "query_kg":
        query = KGQuery.model_validate(arguments.root)
        result = query_kg(db, query, access=access)
        refs = [entity.asset_ref for entity in result.entities]
        refs.extend(
            anchor.asset_ref
            for relation in result.relations
            for anchor in relation.assertion.anchors
        )
        if result.dataset_id:
            refs.append(AssetRef(asset_id=result.dataset_id, version=result.version_id))
        return FunctionResult(function=name, asset_refs=refs, data=result.model_dump(mode="json"))
    params = KGExplainQuery.model_validate(arguments.root)
    explanation = explain_relation(db, params.assertion_id, access=access)
    return FunctionResult(
        function=name,
        asset_refs=[
            explanation.relation.head.asset_ref,
            explanation.relation.tail.asset_ref,
            *(source.asset_ref for source in explanation.sources),
        ],
        data=explanation.model_dump(mode="json"),
    )
