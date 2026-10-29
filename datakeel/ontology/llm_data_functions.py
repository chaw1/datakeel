# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Expose offline training measurements through the shared Agent and MCP read boundary."""

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.llm_data_governance import TrainingQualityQuery
from datakeel.core.models import JsonDocument
from datakeel.ontology.models import FunctionResult
from datakeel.storage.database import Database
from datakeel.storage.llm_data_reads import read_training_result


def invoke_llm_data(
    db: Database, arguments: JsonDocument, *, access: AccessContext | None = None
) -> FunctionResult:
    """Keep reads read-only while returning real counts, redacted evidence and source refs."""
    query = TrainingQualityQuery.model_validate(arguments.root)
    result = read_training_result(db, query, access=access)
    report = result.report
    return FunctionResult(
        function="get_training_quality",
        asset_refs=list(result.asset_refs),
        data=report.model_dump(mode="json"),
    )
