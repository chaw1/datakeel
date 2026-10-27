# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read monitored failures and table quality through the shared tool registry."""

from typing import Literal

from pydantic import Field

from datakeel.core.catalog_models import CatalogObject, CatalogQuery
from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.models import AssetRef, BoundaryModel, JsonDocument
from datakeel.ontology.models import FunctionResult
from datakeel.storage.catalog_queries import read_objects
from datakeel.storage.database import Database
from datakeel.storage.dq_reads import read_results
from datakeel.storage.dq_views import read_rule_views, read_summary


class QualityRulesParams(BoundaryModel):
    """Filter current rules by exact source, table, schema and observation status."""

    source_id: str | None = None
    table: str | None = None
    schema_name: str | None = None
    status: Literal["passed", "failed", "error", "baseline_insufficient", "pending"] | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class TableQualityParams(BoundaryModel):
    """Read a table's latest score and a bounded history for each associated rule."""

    source_id: str = Field(min_length=1)
    table: str = Field(min_length=1)
    schema_name: str | None = None
    history_limit: int = Field(default=10, ge=1, le=100)


def invoke_quality(db: Database, name: str, arguments: JsonDocument) -> FunctionResult:
    """Return only persisted read projections; never enqueue or query a business source."""
    if name == "list_quality_rules":
        params = QualityRulesParams.model_validate(arguments.root)
        views = read_rule_views(db, params.source_id, params.table, params.schema_name)
        matches = tuple(
            view
            for view in views
            if params.status is None
            or params.status == (view.latest_result.status if view.latest_result else "pending")
        )
        selected = matches[: params.limit]
        return FunctionResult(
            function=name,
            asset_refs=[
                AssetRef(asset_type="quality_rule", asset_id=view.rule.id) for view in selected
            ],
            data={
                "items": [view.model_dump(mode="json") for view in selected],
                "total": len(matches),
            },
        )
    params = TableQualityParams.model_validate(arguments.root)
    table = _resolve_table(db, params)
    summary = read_summary(db, params.source_id, params.table, table.schema_name)
    return FunctionResult(
        function=name,
        asset_refs=[table.asset_ref],
        data={
            "summary": summary.model_dump(mode="json"),
            "trends": [
                {
                    "rule_id": view.rule.id,
                    "results": [
                        value.model_dump(mode="json")
                        for value in read_results(db, view.rule.id, params.history_limit)
                    ],
                }
                for view in summary.rules
            ],
        },
    )


def _resolve_table(db: Database, params: TableQualityParams) -> CatalogObject:
    candidates = [
        item
        for item in read_objects(
            db,
            CatalogQuery(kind="table", source_id=params.source_id, search=params.table, limit=1000),
        ).items
        if item.name == params.table
        and (params.schema_name is None or item.schema_name == params.schema_name)
    ]
    if not candidates:
        msg = "Table quality target is not in the catalog"
        raise NotFoundError(msg)
    if len(candidates) != 1:
        msg = "Table quality target is ambiguous; specify schema_name"
        raise ValidationError(msg)
    return candidates[0]
