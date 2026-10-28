# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-only standard coverage and confirmed usage shared by Agent and MCP."""

from datakeel.core.models import AssetRef, JsonDocument
from datakeel.core.standard_reporting_models import StandardCoverageParams, StandardUsageParams
from datakeel.ontology.models import FunctionResult
from datakeel.storage.database import Database
from datakeel.storage.standard_queries import standards_report
from datakeel.storage.standard_store import get_contract

STANDARD_TOOL_DESCRIPTIONS = {
    "query_standard_coverage": (
        "Read data standards coverage, worst compliant tables and violation Top N. "
        "数据标准覆盖率、哪张表落标最差、违规排行。"
    ),
    "list_standard_usage": (
        "Read human-confirmed columns using a field standard by code or bilingual name. "
        "查询客户编号等字段标准被哪些列使用。"
    ),
}


def invoke_standard(db: Database, name: str, arguments: JsonDocument) -> FunctionResult:
    """Answer standard questions from confirmed state without exposing raw profile values."""
    if name == "query_standard_coverage":
        params = StandardCoverageParams.model_validate(arguments.root)
        report = standards_report(db, params.table_id)
        ranking = sorted(
            report.coverage.tables, key=lambda item: (item.compliance, item.coverage, item.key)
        )[: params.limit]
        return FunctionResult(
            function=name,
            asset_refs=[AssetRef(asset_type="table", asset_id=item.key) for item in ranking],
            data={
                "coverage": report.coverage.model_dump(mode="json"),
                "worst_tables": [item.model_dump(mode="json") for item in ranking],
            },
        )
    params = StandardUsageParams.model_validate(arguments.root)
    query = params.standard.casefold()
    contract = get_contract(db)
    standards = [
        item
        for item in contract.standards
        if query
        in {value.casefold() for value in (item.code, item.name_zh, item.name_en, *item.aliases)}
    ]
    exact = [item for item in standards if item.code.casefold() == query]
    codes = {item.code for item in exact or standards}
    report = standards_report(db)
    selected = [item for item in report.mappings if item.standard_code in codes]
    return FunctionResult(
        function=name,
        asset_refs=[
            AssetRef(asset_type="column", asset_id=item.column_id)
            for item in selected[: params.limit]
        ],
        data={
            "standards": [item.model_dump(mode="json") for item in exact or standards],
            "mappings": [item.model_dump(mode="json") for item in selected[: params.limit]],
            "total": len(selected),
        },
    )
