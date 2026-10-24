# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Registered metadata and question functions shared by Agent and MCP dispatch."""

from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.core.knowledge_citations import knowledge_citations
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.ontology.catalog_parameters import ImpactParams, MetricListParams, MetricParams
from datakeel.ontology.models import FunctionResult
from datakeel.storage import catalog_queries, metric_store
from datakeel.storage.database import Database


def _ask(db: Database, arguments: JsonDocument) -> FunctionResult:
    answer = ask_data(db, AskRequest.model_validate(arguments.root))
    refs = [AssetRef(asset_type="question", asset_id=answer.id, version=answer.id)]
    if answer.metric_card is not None:
        metric = answer.metric_card.definition
        refs.append(AssetRef(asset_type="metric", asset_id=metric.id, version=str(metric.version)))
    if answer.sql is not None:
        refs.extend(
            AssetRef(asset_type="table", asset_id=identity) for identity in answer.sql.tables
        )
        refs.extend(
            AssetRef(asset_type="column", asset_id=identity) for identity in answer.sql.columns
        )
    refs.extend(ref for ref in knowledge_citations(answer.knowledge) if ref not in refs)
    omitted: set[str] = (
        {"answer_kind", "knowledge", "subject_candidates"}
        if (answer.answer_kind == "metric" and answer.knowledge is None)
        else set()
    )
    return FunctionResult(
        function="ask_data",
        asset_refs=refs,
        data=answer.model_dump(mode="json", exclude=omitted),
    )


def _metrics(db: Database, arguments: JsonDocument) -> FunctionResult:
    params = MetricListParams.model_validate(arguments.root)
    cards = [
        card
        for card in metric_store.list_metrics(db)
        if (params.status is None or params.status == card.status)
        and (
            params.search is None
            or params.search.casefold() in card.definition.name.casefold()
            or params.search.casefold() in card.definition.id.casefold()
        )
    ]
    selected = cards[params.offset : params.offset + params.limit]
    refs = [
        AssetRef(
            asset_type="metric", asset_id=card.definition.id, version=str(card.definition.version)
        )
        for card in selected
    ]
    return FunctionResult(
        function="list_metrics",
        asset_refs=refs,
        data={
            "items": [card.model_dump(mode="json") for card in selected],
            "total": len(cards),
            "offset": params.offset,
            "limit": params.limit,
        },
    )


def invoke_catalog(db: Database, name: str, arguments: JsonDocument) -> FunctionResult:
    """Validate registered metadata reads and preserve all addressed asset identities."""
    if name == "ask_data":
        return _ask(db, arguments)
    if name == "list_metrics":
        return _metrics(db, arguments)
    if name == "explain_metric":
        metric = metric_store.get_metric(db, MetricParams.model_validate(arguments.root).metric_id)
        return FunctionResult(
            function=name,
            asset_refs=[
                AssetRef(
                    asset_type="metric",
                    asset_id=metric.definition.id,
                    version=str(metric.definition.version),
                )
            ],
            data=metric.model_dump(mode="json"),
        )
    params = ImpactParams.model_validate(arguments.root)
    result = catalog_queries.impact(db, params.asset_id, params.max_nodes)
    return FunctionResult(
        function=name,
        asset_refs=[item.asset_ref for item in result.objects],
        data=result.model_dump(mode="json"),
    )
