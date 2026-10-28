# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Parse, resolve, compile, execute, explain, and persist local evidence-backed answers."""

from pydantic import ValidationError as ModelValidationError

from datakeel.ask.access import answer_refs, query_refs
from datakeel.ask.charts import answer_chart
from datakeel.ask.comparisons import (
    comparison_changes,
    comparison_message,
    comparison_unit_mismatch,
)
from datakeel.ask.consumption import leftover_fragments
from datakeel.ask.followup import (
    MetricTurn,
    interpreted_question,
    prepare_metric_turn,
    previous_period,
)
from datakeel.ask.knowledge_parser import metric_recognition, parse_knowledge_question
from datakeel.ask.knowledge_service import knowledge_answer, related_knowledge
from datakeel.ask.models import DimensionParse, Leftovers, QueryContext
from datakeel.ask.profile import parse_profile_question, profile_answer
from datakeel.core.ask_frame_models import AskComparison, AskQueryFrame
from datakeel.core.ask_models import (
    AskAnswer,
    AskInterpretation,
    AskRequest,
    LineageReference,
    MetricResolution,
    ParsedQuestion,
)
from datakeel.core.catalog_models import CatalogSnapshot, SourceProperties
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import ExecutionError, NotFoundError, ValidationError
from datakeel.core.metric_models import CompiledQuery, CompileRequest, MetricCard, QueryResult
from datakeel.core.models import new_id
from datakeel.metrics.compiler import compile_metric
from datakeel.metrics.execution import execute_query
from datakeel.metrics.projection import resolved_metric_cards, semantic_layer
from datakeel.storage.ask_conversations import get_conversation, store_conversation_turn
from datakeel.storage.catalog_store import read_snapshot
from datakeel.storage.data_asset_access import require_access
from datakeel.storage.database import Database
from datakeel.storage.link_queries import read_link_context
from datakeel.storage.profile_queries import read_profiles


def ask_data(
    db: Database,
    request: AskRequest,
    *,
    access: AccessContext | None = None,
    record_usage: bool = True,
) -> AskAnswer:
    """Answer only from registered metadata and store every outcome with its evidence."""
    caller = (access or AccessContext(actor=request.actor, entry="ask", scope="query")).model_copy(
        update={"scope": "query"}
    )
    request = request.model_copy(update={"actor": caller.actor})
    previous = (
        get_conversation(db, request.conversation_id, caller.actor)
        if request.conversation_id is not None
        else None
    )
    request = request.model_copy(update={"conversation_id": request.conversation_id or new_id()})
    answer = _ask_data(db, request, caller, previous.current_frame if previous else None)
    answer = answer.model_copy(
        update={
            "conversation_id": request.conversation_id,
            "interpreted_question": answer.interpreted_question
            or interpreted_question(answer.query_frame, answer.metric_card, request.question),
        }
    )
    answer = answer_chart(answer)
    require_access(db, answer_refs(answer), caller, record=record_usage)
    return store_conversation_turn(db, request, answer, previous)


def _ask_data(
    db: Database, request: AskRequest, access: AccessContext, previous: AskQueryFrame | None
) -> AskAnswer:
    profile = parse_profile_question(request)
    if profile is not None:
        return profile_answer(request, profile, read_profiles(db))
    with db.session() as session:
        snapshot = read_snapshot(session)
    context = QueryContext(snapshot=snapshot, layer=semantic_layer(snapshot))
    graph = read_link_context(db)
    turn = prepare_metric_turn(request, context.layer, resolved_metric_cards(snapshot), previous)
    knowledge = parse_knowledge_question(
        request.question,
        snapshot,
        context.layer,
        graph,
        subject_id=request.subject_id or request.metric_id,
    )
    contextual_metric = (
        turn.follows
        and knowledge is not None
        and (
            (
                bool(knowledge.intent_candidates)
                and any(item.metric_id for item in turn.parsed.matches)
            )
            or turn.resolution.status == "resolved"
        )
    )
    if knowledge is not None and not contextual_metric:
        require_access(
            db, tuple(item.asset_ref for item in knowledge.candidates), access, record=False
        )
        return knowledge_answer(db, request, knowledge, snapshot, context.layer, graph).model_copy(
            update={"recognition": knowledge.recognition}
        )
    if turn.resolution.status != "resolved":
        answer = _nonanswer(request, turn.parsed, turn.resolution).model_copy(
            update={
                "interpretation": _interpretation(turn.parsed, turn.resolution, turn.dimensions),
                "query_frame": previous if turn.follows else None,
            }
        )
    else:
        answer = _answer(db, request, turn, context, access)
        answer = related_knowledge(db, answer, snapshot, graph)
    return answer.model_copy(
        update={"recognition": metric_recognition(request.question, snapshot, context.layer)}
    )


def _answer(
    db: Database,
    request: AskRequest,
    turn: MetricTurn,
    context: QueryContext,
    access: AccessContext,
) -> AskAnswer:
    parsed, resolution, dimensions = turn.parsed, turn.resolution, turn.dimensions
    card = resolution.candidates[0]
    frame = turn.frame
    if frame is None:
        msg = "Resolved metric turn has no query frame"
        raise ValidationError(msg)
    interpreted = dimensions.model_copy(update={"slices": frame.slices, "group_by": frame.group_by})
    parsed = parsed.model_copy(update={"time_range": frame.time_range})
    interpretation = _interpretation(parsed, resolution, interpreted)
    extra = dimensions.model_copy(update={"consumed": dimensions.consumed + turn.consumed})
    refusal = _frame_refusal(resolution, frame, request.question) or _condition_refusal(
        resolution, dimensions, _leftovers(parsed, extra)
    )
    if refusal is not None:
        return _nonanswer(request, parsed, refusal).model_copy(
            update={
                "interpretation": interpretation,
                "query_frame": turn.previous_frame,
            }
        )
    try:
        query, result, comparison = _execute_frame(db, context, frame, card, access)
    except (ExecutionError, NotFoundError, ValidationError, ModelValidationError) as exc:
        refusal = MetricResolution(
            status="unanswerable",
            candidates=resolution.candidates,
            message=f"已登记指标暂时无法执行 ({type(exc).__name__})。",
        )
        return _nonanswer(request, parsed, refusal).model_copy(
            update={"interpretation": interpretation, "query_frame": turn.previous_frame}
        )
    return AskAnswer(
        session_id=request.session_id or new_id(),
        question=request.question,
        status="answered",
        message=comparison_message(comparison),
        reference_instant=request.reference_instant,
        metric_card=card,
        sql=query,
        result=result,
        comparison=comparison,
        query_frame=frame,
        interpreted_question=interpreted_question(frame, card, request.question, context.layer),
        time_range=frame.time_range,
        matches=parsed.matches,
        lineage=LineageReference(asset_id=card.definition.id),
        interpretation=interpretation,
    )


def _frame_refusal(
    resolution: MetricResolution, frame: AskQueryFrame, question: str
) -> MetricResolution | None:
    if frame.share_of_result_rows and not (frame.group_by or frame.time_grain):
        return resolution.model_copy(
            update={"status": "clarification", "message": "结果行占比需要明确分组维度或时间粒度。"}
        )
    if comparison_unit_mismatch(question, frame):
        return resolution.model_copy(
            update={
                "status": "clarification",
                "message": "指定的对比周期与当前完整时间区间不一致。请明确月份或季度。",
            }
        )
    if frame.comparison and previous_period(frame, frame.comparison) is None:
        return _comparison_refusal(resolution, frame)
    return None


def _comparison_refusal(resolution: MetricResolution, frame: AskQueryFrame) -> MetricResolution:
    label = "同比" if frame.comparison == "year_over_year" else "环比"
    return resolution.model_copy(
        update={"status": "clarification", "message": f"请明确{label}的时间范围。"}
    )


def _compile_frame(
    context: QueryContext, frame: AskQueryFrame, card: MetricCard
) -> tuple[SourceProperties, CompiledQuery]:
    source = _source(context.snapshot, card)
    dialect = "postgres" if source.dialect in {"postgres", "postgresql"} else "sqlite"
    query = compile_metric(
        card,
        context.layer.dimensions,
        CompileRequest(
            dialect=dialect,
            slices=list(frame.slices),
            group_by=list(frame.group_by),
            time_range=frame.time_range,
            time_grain=frame.time_grain,
        ),
    )
    return source, query


def _execute_frame(
    db: Database,
    context: QueryContext,
    frame: AskQueryFrame,
    card: MetricCard,
    access: AccessContext,
) -> tuple[CompiledQuery, QueryResult, AskComparison | None]:
    source, query = _compile_frame(context, frame, card)
    require_access(db, query_refs(query), access, record=False)
    result = execute_query(source.connection_url or "", query)
    comparison = None
    interval = previous_period(frame, frame.comparison) if frame.comparison else None
    if interval is not None and frame.comparison is not None:
        _, prior_query = _compile_frame(
            context, frame.model_copy(update={"time_range": interval}), card
        )
        require_access(db, query_refs(prior_query), access, record=False)
        previous = execute_query(source.connection_url or "", prior_query)
        comparison = AskComparison(
            mode=frame.comparison,
            previous_time_range=interval,
            previous_sql=prior_query,
            previous_result=previous,
            changes=comparison_changes(result, previous, frame, interval),
        )
    return query, result, comparison


def _leftovers(parsed: ParsedQuestion, dimensions: DimensionParse) -> Leftovers:
    spans = [(item.start, item.end) for item in parsed.matches]
    times = tuple((item.start, item.end) for item in parsed.matches if item.match_kind == "time")
    return leftover_fragments(parsed.question, [*spans, *dimensions.consumed], times)


def _condition_refusal(
    resolution: MetricResolution, dimensions: DimensionParse, leftovers: Leftovers
) -> MetricResolution | None:
    """Never execute when a temporal, filter or grouping fragment was not understood."""
    if leftovers.times:
        return MetricResolution(
            status="unanswerable",
            candidates=resolution.candidates,
            message="无法可靠解析时间条件: 未理解「" + "」「".join(leftovers.times) + "」",
        )
    rankings = () if dimensions.group_by else leftovers.rankings
    unsupported = [*leftovers.calculations, *rankings]
    if unsupported:
        return MetricResolution(
            status="unanswerable",
            candidates=resolution.candidates,
            message="登记指标不支持所问的计算: 「" + "」「".join(unsupported) + "」",
        )
    issues = [*dimensions.issues, *(f"未理解「{item}」" for item in leftovers.conditions)]
    if issues:
        return MetricResolution(
            status="clarification",
            candidates=resolution.candidates,
            message="请明确维度条件: " + "; ".join(issues),
        )
    return None


def _interpretation(
    parsed: ParsedQuestion, resolution: MetricResolution, dimensions: DimensionParse
) -> AskInterpretation:
    resolved = resolution.status == "resolved" and len(resolution.candidates) == 1
    as_of = any(item.source.startswith("time:as_of") for item in parsed.matches)
    leftovers = _leftovers(parsed, dimensions)
    return AskInterpretation(
        metric_id=resolution.candidates[0].definition.id if resolved else None,
        time_range=parsed.time_range,
        time_basis=None if parsed.time_range is None else "as_of" if as_of else "period",
        slices=dimensions.slices,
        group_by=dimensions.group_by,
        unconsumed=(
            *leftovers.times,
            *leftovers.conditions,
            *leftovers.calculations,
            *leftovers.rankings,
        ),
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
