# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Word the effective query slots in English for an English interface."""

from datakeel.core.ask_frame_models import AskQueryFrame
from datakeel.core.metric_models import MetricCard, SemanticLayer

_GRAINS = {"day": "day", "month": "month", "quarter": "quarter", "year": "year"}


def interpreted_question_en(
    frame: AskQueryFrame | None,
    card: MetricCard | None,
    question: str,
    layer: SemanticLayer | None = None,
) -> str:
    """Express the same slots as the Chinese interpretation; registered values stay as recorded.

    Metric and dimension names use their registered English names when they have one.
    Without a frame and metric there is nothing interpreted, so the question is returned.
    """
    if frame is None or card is None:
        return question
    names = {item.id: item.english_name or item.name for item in layer.dimensions} if layer else {}
    parts = [f"Query {card.definition.english_name or card.definition.name}"]
    if frame.time_range:
        parts.append(f"from {frame.time_range.start} to {frame.time_range.end} (end date excluded)")
    parts.extend(
        f"where {names.get(item.dimension_id, item.dimension_id)} is {item.value}"
        for item in frame.slices
    )
    if frame.group_by:
        parts.append("grouped by " + ", ".join(names.get(item, item) for item in frame.group_by))
    if frame.time_grain:
        parts.append(f"split by {_GRAINS[frame.time_grain]}")
    if frame.comparison:
        parts.append(
            "compared with the same period last year"
            if frame.comparison == "year_over_year"
            else "compared with the previous period"
        )
    if frame.share_of_result_rows:
        parts.append(
            "showing each row's share of the returned rows' total "
            "(not computed when the total is 0)"
        )
    return ", ".join(parts) + "."
