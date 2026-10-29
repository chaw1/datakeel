# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve deterministic query edits while preserving the single-question parser guards."""

from datakeel.ask import followup_cues as cues
from datakeel.ask.dimensions import dimension_mentions, parse_dimensions
from datakeel.ask.followup_frames import inherit_frame
from datakeel.ask.matching import metric_matches
from datakeel.ask.models import DimensionParse
from datakeel.ask.parser import parse_question
from datakeel.ask.resolution import resolve_metric
from datakeel.ask.time_atoms import shift_months
from datakeel.core.ask_frame_models import AskQueryFrame, ComparisonMode, TimeGrain
from datakeel.core.ask_models import AskRequest, MatchEvidence, MetricResolution, ParsedQuestion
from datakeel.core.metric_models import MetricCard, SemanticLayer, TimeRange
from datakeel.core.models import BoundaryModel


class MetricTurn(BoundaryModel):
    """Carry one resolved parse and complete inherited query intent to execution."""

    parsed: ParsedQuestion
    resolution: MetricResolution
    dimensions: DimensionParse = DimensionParse()
    frame: AskQueryFrame | None = None
    consumed: tuple[tuple[int, int], ...] = ()
    follows: bool = False
    previous_frame: AskQueryFrame | None = None


def prepare_metric_turn(
    request: AskRequest,
    layer: SemanticLayer,
    cards: list[MetricCard],
    previous: AskQueryFrame | None,
) -> MetricTurn:
    """Apply only recognized edits; a complete metric question starts a fresh frame."""
    cleaned, consumed, comparison, grain = _specials(request.question, layer)
    consumed.extend(cues.switch_spans(request.question))
    parsed = parse_question(request.model_copy(update={"question": cleaned}), layer).model_copy(
        update={"question": request.question}
    )
    parsed = parsed.model_copy(
        update={"matches": parsed.matches + _special_matches(request.question, consumed)}
    )
    if previous is not None:
        consumed.extend(cues.continuation_spans(request.question))
    has_metric = any(item.metric_id for item in parsed.matches)
    follows = previous is not None and (
        _continues_metric(request.question, parsed)
        if has_metric
        else _continues_frame(request.question, parsed, consumed, layer)
    )
    resolution = _turn_resolution(request, parsed, cards, previous if follows else None)
    if resolution.status != "resolved":
        if follows:
            resolution = resolution.model_copy(update={"status": "clarification"})
        return MetricTurn(parsed=parsed, resolution=resolution, follows=follows)
    card = resolution.candidates[0]
    occupied = tuple((item.start, item.end) for item in parsed.matches if item.metric_id)
    dimensions = parse_dimensions(cleaned, card, layer, occupied)
    inherited = inherit_frame(previous, card, layer) if follows and previous else None
    if follows and inherited is None:
        return MetricTurn(
            parsed=parsed,
            resolution=resolution.model_copy(
                update={
                    "status": "clarification",
                    "message": "新指标无法明确沿用上一轮维度,请明确筛选和分组。",
                }
            ),
            follows=True,
        )
    turn = _resolved(parsed, resolution, dimensions, inherited)
    return _apply_edits(request, turn, previous if follows else None, comparison, grain, consumed)


def _apply_edits(
    request: AskRequest,
    turn: MetricTurn,
    previous: AskQueryFrame | None,
    comparison: ComparisonMode | None,
    grain: TimeGrain | None,
    consumed: list[tuple[int, int]],
) -> MetricTurn:
    follows = previous is not None
    frame = turn.frame
    if frame is None:
        return turn
    frame = frame.model_copy(
        update={
            "comparison": comparison if comparison is not None else frame.comparison,
            "time_grain": grain if grain is not None else frame.time_grain,
            "share_of_result_rows": frame.share_of_result_rows
            or any(cues.SHARE.fullmatch(request.question[start:end]) for start, end in consumed),
        }
    )
    same = cues.SAME_PERIOD.fullmatch(request.question.strip(" ?\uff1f呢。"))
    if same and previous is not None:
        interval = previous_period(previous, "year_over_year")
        if interval is None:
            return turn.model_copy(
                update={
                    "resolution": turn.resolution.model_copy(
                        update={
                            "status": "clarification",
                            "message": "请明确同期对应的有界时间区间。",
                        }
                    ),
                    "follows": True,
                }
            )
        frame = frame.model_copy(update={"time_range": interval, "comparison": previous.comparison})
        consumed.append((0, len(request.question)))
    turn = turn.model_copy(
        update={
            "frame": frame,
            "consumed": tuple(consumed),
            "follows": follows,
            "previous_frame": previous if follows else None,
        }
    )
    return _validate_followup(request, turn) if follows else turn


def _continues_metric(question: str, parsed: ParsedQuestion) -> bool:
    spans = [(item.start, item.end) for item in parsed.matches if item.metric_id]
    noun_only = not cues.unknown_followup(question, spans)
    suffix = question.rstrip(" ?\uff1f。").endswith("呢")
    return cues.metric_switch(question) or (suffix and noun_only)


def _continues_frame(
    question: str, parsed: ParsedQuestion, consumed: list[tuple[int, int]], layer: SemanticLayer
) -> bool:
    """Edit the saved frame only for sentences that signal an edit or are fully understood."""
    mentions = dimension_mentions(question, layer)
    spans = [
        *((item.start, item.end) for item in parsed.matches),
        *((item.start, item.end) for item in mentions),
    ]
    if cues.fresh_question(question, [*spans, *consumed]):
        return False
    if cues.edit_cue(question) or consumed:
        return True
    if any(item.match_kind == "dimension_value" for item in mentions):
        return True
    return not cues.unknown_followup(question, spans)


def _turn_resolution(
    request: AskRequest,
    parsed: ParsedQuestion,
    cards: list[MetricCard],
    previous: AskQueryFrame | None,
) -> MetricResolution:
    resolution = resolve_metric(parsed, cards, request.metric_id)
    if (
        previous
        and not any(item.metric_id for item in parsed.matches)
        and request.metric_id is None
    ):
        resolution = _inherited_resolution(parsed, cards, previous.metric_id)
    if cues.conflicting_edits(request.question):
        resolution = resolution.model_copy(
            update={
                "status": "clarification",
                "message": "请明确需要的对比方式和时间分组,不支持否定或相互冲突的修改。",
            }
        )
    return resolution


def _special_matches(question: str, consumed: list[tuple[int, int]]) -> tuple[MatchEvidence, ...]:
    return tuple(
        MatchEvidence(
            start=start,
            end=end,
            text=question[start:end],
            source="query:intent",
            match_kind="normalized",
        )
        for start, end in consumed
    )


def _specials(
    question: str, layer: SemanticLayer
) -> tuple[str, list[tuple[int, int]], ComparisonMode | None, TimeGrain | None]:
    consumed: list[tuple[int, int]] = []
    comparison: ComparisonMode | None = None
    grain: TimeGrain | None = None
    occupied = tuple((item.start, item.end) for item in metric_matches(question, layer))
    consumed.extend(cues.share_spans(question, occupied))
    for mode, hit in cues.comparison_hits(question):
        comparison = mode
        consumed.append(hit.span())
    for value, pattern in cues.GRAINS:
        for hit in pattern.finditer(question):
            grain = value
            consumed.append(hit.span())
    masked = list(question)
    for start, end in consumed:
        masked[start:end] = " " * (end - start)
    return "".join(masked), consumed, comparison, grain


def _inherited_resolution(
    parsed: ParsedQuestion, cards: list[MetricCard], identity: str
) -> MetricResolution:
    candidates = tuple(card for card in cards if card.definition.id == identity)
    valid = bool(candidates) and candidates[0].status == "resolved" and not parsed.issues
    if valid:
        message = "已复用上一轮指标,并重新检查当前登记口径。"
    elif parsed.issues:
        message = "追问的时间条件不可用: " + "; ".join(parsed.issues)
    else:
        message = "上一轮指标在当前登记口径下不可用。"
    return MetricResolution(
        status="resolved" if valid else "clarification", candidates=candidates, message=message
    )


def _resolved(
    parsed: ParsedQuestion,
    resolution: MetricResolution,
    dimensions: DimensionParse,
    previous: AskQueryFrame | None,
) -> MetricTurn:
    slices = {item.dimension_id: item for item in previous.slices} if previous else {}
    slices.update({item.dimension_id: item for item in dimensions.slices})
    sliced = {item.dimension_id for item in dimensions.slices}
    inherited_groups = set(previous.group_by if previous else ()) - sliced
    groups = tuple(sorted(inherited_groups | set(dimensions.group_by)))
    frame = AskQueryFrame(
        metric_id=resolution.candidates[0].definition.id,
        time_range=parsed.time_range or (previous.time_range if previous else None),
        time_basis=("as_of" if any("as_of" in item.source for item in parsed.matches) else "period")
        if parsed.time_range
        else previous.time_basis
        if previous
        else None,
        slices=tuple(slices[key] for key in sorted(slices)),
        group_by=groups,
        time_grain=previous.time_grain if previous else None,
        comparison=previous.comparison if previous else None,
        share_of_result_rows=previous.share_of_result_rows if previous else False,
    )
    return MetricTurn(
        parsed=parsed.model_copy(update={"matches": parsed.matches + dimensions.matches}),
        resolution=resolution,
        dimensions=dimensions,
        frame=frame,
        follows=previous is not None,
    )


def _validate_followup(request: AskRequest, turn: MetricTurn) -> MetricTurn:
    spans = [
        *((item.start, item.end) for item in turn.parsed.matches),
        *turn.dimensions.consumed,
        *turn.consumed,
    ]
    unknown = cues.unknown_followup(request.question, spans)
    particles = set(cues.continuation_spans(request.question))
    understood = bool(
        turn.parsed.matches or turn.dimensions.consumed or set(turn.consumed) - particles
    )
    if unknown or not understood:
        return turn.model_copy(
            update={
                "resolution": turn.resolution.model_copy(
                    update={
                        "status": "clarification",
                        "message": "无法确定追问的修改内容,请明确指标、时间、维度取值或分组。",
                    }
                )
            }
        )
    return turn


def previous_period(frame: AskQueryFrame, mode: ComparisonMode) -> TimeRange | None:
    """Shift calendar-aligned intervals by year or by their exact previous period."""
    interval = frame.time_range
    if interval is None or frame.time_basis == "as_of":
        return None
    try:
        return _shifted_period(interval, mode)
    except (ValueError, OverflowError):
        return None


def _shifted_period(interval: TimeRange, mode: ComparisonMode) -> TimeRange:
    if mode == "year_over_year":
        return TimeRange(
            start=shift_months(interval.start, -12), end=shift_months(interval.end, -12)
        )
    months = (
        (interval.end.year - interval.start.year) * 12 + interval.end.month - interval.start.month
    )
    if interval.start.day == interval.end.day == 1 and months > 0:
        return TimeRange(start=shift_months(interval.start, -months), end=interval.start)
    return TimeRange(start=interval.start - (interval.end - interval.start), end=interval.start)


def interpreted_question(
    frame: AskQueryFrame | None,
    card: MetricCard | None,
    question: str,
    layer: SemanticLayer | None = None,
) -> str:
    """Express every effective query slot in a complete auditable question."""
    if frame is None or card is None:
        return question
    names = {item.id: item.name for item in layer.dimensions} if layer else {}
    parts = [f"查询{card.definition.name}"]
    if frame.time_range:
        parts.append(f"时间从{frame.time_range.start}至{frame.time_range.end}(不含结束日)")
    parts.extend(
        f"筛选{names.get(item.dimension_id, item.dimension_id)}为{item.value}"
        for item in frame.slices
    )
    if frame.group_by:
        parts.append("按" + "、".join(names.get(item, item) for item in frame.group_by) + "分组")
    if frame.time_grain:
        parts.append(
            "按"
            + {"day": "日", "month": "月", "quarter": "季度", "year": "年"}[frame.time_grain]
            + "拆分"
        )
    if frame.comparison:
        parts.append("与去年同期比较" if frame.comparison == "year_over_year" else "与上一期比较")
    if frame.share_of_result_rows:
        parts.append("显示结果行占比,分母为当前返回结果行总和(总和为0时不计算)")
    return ",".join(parts) + "。"
