# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Parse, resolve, compile, execute, explain, and persist local evidence-backed answers."""

from pydantic import ValidationError as ModelValidationError

from datakeel.ask.dimensions import parse_dimensions
from datakeel.ask.models import QueryContext
from datakeel.ask.parser import parse_question
from datakeel.ask.resolution import resolve_metric
from datakeel.core.ask_models import (
    AskAnswer,
    AskRequest,
    LineageReference,
    MetricResolution,
    ParsedQuestion,
)
from datakeel.core.catalog_models import CatalogSnapshot, SourceProperties
from datakeel.core.errors import ExecutionError, NotFoundError, ValidationError
from datakeel.core.metric_models import CompileRequest, MetricCard
from datakeel.core.models import new_id
from datakeel.metrics.compiler import compile_metric
from datakeel.metrics.execution import execute_query
from datakeel.metrics.projection import resolved_metric_cards, semantic_layer
from datakeel.storage.ask_store import store_answer
from datakeel.storage.catalog_store import read_snapshot
from datakeel.storage.database import Database


def ask_data(db: Database, request: AskRequest) -> AskAnswer:
    """Answer only from registered metadata and store every outcome with its evidence."""
    with db.session() as session:
        snapshot = read_snapshot(session)
    context = QueryContext(snapshot=snapshot, layer=semantic_layer(snapshot))
    parsed = parse_question(request, context.layer)
    resolution = resolve_metric(parsed, resolved_metric_cards(snapshot), request.metric_id)
    if resolution.status != "resolved":
        answer = _nonanswer(request, parsed, resolution)
    else:
        answer = _answer(request, parsed, resolution, context)
    return store_answer(db, request, answer)


def _answer(
    request: AskRequest, parsed: ParsedQuestion, resolution: MetricResolution, context: QueryContext
) -> AskAnswer:
    card = resolution.candidates[0]
    dimensions = parse_dimensions(request.question, card, context.layer)
    parsed = parsed.model_copy(update={"matches": parsed.matches + dimensions.matches})
    if dimensions.issues:
        refusal = MetricResolution(
            status="clarification",
            candidates=resolution.candidates,
            message="请明确维度条件: " + "; ".join(dimensions.issues),
        )
        return _nonanswer(request, parsed, refusal)
    try:
        source = _source(context.snapshot, card)
        dialect = "postgres" if source.dialect in {"postgres", "postgresql"} else "sqlite"
        query = compile_metric(
            card,
            context.layer.dimensions,
            CompileRequest(
                dialect=dialect,
                slices=list(dimensions.slices),
                group_by=list(dimensions.group_by),
                time_range=parsed.time_range,
            ),
        )
        result = execute_query(source.connection_url or "", query)
    except (ExecutionError, NotFoundError, ValidationError, ModelValidationError) as exc:
        refusal = MetricResolution(
            status="unanswerable",
            candidates=resolution.candidates,
            message=f"已登记指标暂时无法执行 ({type(exc).__name__})。",
        )
        return _nonanswer(request, parsed, refusal)
    return AskAnswer(
        session_id=request.session_id or new_id(),
        question=request.question,
        status="answered",
        message="答案来自登记指标与只读查询。",
        reference_instant=request.reference_instant,
        metric_card=card,
        sql=query,
        result=result,
        time_range=parsed.time_range,
        matches=parsed.matches,
        lineage=LineageReference(asset_id=card.definition.id),
    )


def _nonanswer(
    request: AskRequest, parsed: ParsedQuestion, resolution: MetricResolution
) -> AskAnswer:
    return AskAnswer(
        session_id=request.session_id or new_id(),
        question=request.question,
        status="clarification" if resolution.status == "clarification" else "unanswerable",
        message=resolution.message,
        reference_instant=request.reference_instant,
        time_range=parsed.time_range,
        matches=parsed.matches,
        candidates=resolution.candidates,
    )


def _source(snapshot: CatalogSnapshot, card: MetricCard) -> SourceProperties:
    source_id = card.definition.measure.table.split("/")[0]
    for item in snapshot.objects:
        if item.asset_ref.asset_type == "source" and item.asset_ref.asset_id == source_id:
            source = SourceProperties.model_validate(item.properties.root)
            if source.connection_url and source.dialect in {"sqlite", "postgres", "postgresql"}:
                return source
            msg = "Metric source has no supported read-only database connection"
            raise ValidationError(msg)
    msg = f"Registered metric source not found: {source_id}"
    raise NotFoundError(msg)
