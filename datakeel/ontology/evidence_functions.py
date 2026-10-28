# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed evidence reads shared by the resident Agent and MCP catalog."""

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.evidence.query_models import EvidenceQuery
from datakeel.ontology.models import FunctionResult
from datakeel.ontology.parameters import EvidenceAssetParams
from datakeel.storage import evidence_queries
from datakeel.storage.database import Database


def invoke_evidence(
    db: Database, name: str, arguments: JsonDocument, *, access: AccessContext | None = None
) -> FunctionResult:
    """Validate evidence parameters and preserve sample or requested scope identities."""
    if name == "query_evidence":
        query = EvidenceQuery.model_validate(arguments.root)
        result = evidence_queries.query_evidence(db, query, access=access)
        refs = [item.asset_ref for item in result.items]
        if not refs and query.dataset_id:
            refs = [AssetRef(asset_type="dataset", asset_id=query.dataset_id)]
        if not refs:
            refs = [
                AssetRef(asset_type="version", asset_id=version, version=version)
                for version in query.version_ids
            ]
        return FunctionResult(function=name, asset_refs=refs, data=result.model_dump(mode="json"))
    params = EvidenceAssetParams.model_validate(arguments.root)
    sample = (
        evidence_queries.get_evidence(db, params.asset_id, params.version_id, access=access)
        if name == "get_evidence"
        else evidence_queries.explain_sample(db, params.asset_id, params.version_id, access=access)
    )
    return FunctionResult(
        function=name, asset_refs=[sample.asset_ref], data=sample.model_dump(mode="json")
    )
