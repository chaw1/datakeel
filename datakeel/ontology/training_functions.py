# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Expose offline training measurements through the shared Agent and MCP read boundary."""

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.core.training_governance import TrainingQualityQuery
from datakeel.ontology.models import FunctionResult
from datakeel.storage.database import Database
from datakeel.storage.training_reads import read_training_quality


def invoke_training(
    db: Database, arguments: JsonDocument, *, access: AccessContext | None = None
) -> FunctionResult:
    """Keep reads read-only while returning real counts, redacted evidence and source refs."""
    query = TrainingQualityQuery.model_validate(arguments.root)
    report = read_training_quality(db, query, access=access)
    return FunctionResult(
        function="get_training_quality",
        asset_refs=[AssetRef(asset_id=query.dataset_id, version=query.version_id)],
        data=report.model_dump(mode="json"),
    )
