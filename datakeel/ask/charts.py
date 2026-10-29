# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Choose charts deterministically from result shape and registered formatting."""

import re

from datakeel.core.ask_chart_models import ChartSpec, ChartType
from datakeel.core.ask_models import AskAnswer
from datakeel.core.metric_models import MetricDefinition, QueryResult, Scalar

_MAX_CATEGORIES = 30
_VERTICAL_CATEGORIES = 8
_MAX_LABEL_LENGTH = 12
_MAX_DIMENSIONS = 2
_DATE = re.compile(r"^\d{4}(?:-\d{2}(?:-\d{2})?|[- ]?Q[1-4])?$")
_TIME_COLUMNS = frozenset({"time", "date", "day", "month", "quarter", "year", "time_bucket"})
_OPTIONS: dict[ChartType, tuple[ChartType, ...]] = {
    "scalar": ("scalar", "table"),
    "line": ("line", "bar", "horizontal_bar", "table"),
    "bar": ("bar", "horizontal_bar", "table"),
    "horizontal_bar": ("horizontal_bar", "bar", "table"),
    "grouped_bar": ("grouped_bar", "stacked_bar", "table"),
    "stacked_bar": ("grouped_bar", "stacked_bar", "table"),
    "table": ("table",),
}


def select_chart(result: QueryResult, metric: MetricDefinition, *, question: str = "") -> ChartSpec:
    """Select a bounded SVG form and reference original result column identities."""
    numeric = _numeric_columns(result)
    dimensions = [column for column in result.columns if column not in numeric]
    kind = _chart_type(result, numeric, dimensions)
    share = any(cue in question.casefold() for cue in ("占比", "比例", "share", "proportion"))
    if share and kind == "line":
        kind = "bar"
    return ChartSpec(
        type=kind,
        title=metric.name,
        description=f"{metric.name}: {len(result.rows)} result rows; {', '.join(result.columns)}",
        x=dimensions[0] if dimensions else None,
        y=tuple(numeric),
        series=dimensions[1] if len(dimensions) == _MAX_DIMENSIONS else None,
        unit=metric.unit,
        number_format=metric.number_format,
        available_types=_OPTIONS[kind],
        show_percent=share,
    )


def answer_chart(answer: AskAnswer) -> AskAnswer:
    """Attach a descriptor only to executed metric answers with registered units."""
    if answer.status != "answered" or answer.result is None or answer.metric_card is None:
        return answer
    question = answer.question
    if answer.query_frame is not None:
        question = "share" if answer.query_frame.share_of_result_rows else ""
    chart = select_chart(answer.result, answer.metric_card.definition, question=question)
    return answer.model_copy(update={"chart": chart})


def _numeric_columns(result: QueryResult) -> list[str]:
    numeric: list[str] = []
    for index, column in enumerate(result.columns):
        values = [row[index] for row in result.rows if index < len(row) and row[index] is not None]
        if values and all(
            isinstance(value, (int, float)) and not isinstance(value, bool) for value in values
        ):
            numeric.append(column)
    # The metric engine names its measure "value"; numeric dimension keys remain dimensions.
    if "value" in result.columns:
        return ["value"] if "value" in numeric else []
    return numeric


def _chart_type(result: QueryResult, numeric: list[str], dimensions: list[str]) -> ChartType:
    if not numeric or not result.rows or len(dimensions) > _MAX_DIMENSIONS:
        return "table"
    if not dimensions:
        return "scalar" if len(result.rows) == 1 and len(numeric) == 1 else "table"
    categories = _values(result, dimensions[0])
    if len(categories) > _MAX_CATEGORIES or len(numeric) > 1:
        return "table"
    if len(dimensions) == _MAX_DIMENSIONS:
        return "table" if len(_values(result, dimensions[1])) > _MAX_CATEGORIES else "grouped_bar"
    return _single_dimension(dimensions[0], categories)


def _single_dimension(column: str, categories: list[Scalar]) -> ChartType:
    if _temporal(column, categories):
        return "line"
    if len(categories) > _VERTICAL_CATEGORIES or any(
        len(str(value)) > _MAX_LABEL_LENGTH for value in categories
    ):
        return "horizontal_bar"
    return "bar"


def _values(result: QueryResult, column: str) -> list[Scalar]:
    index = result.columns.index(column)
    return list(dict.fromkeys(row[index] for row in result.rows if index < len(row)))


def _temporal(column: str, values: list[Scalar]) -> bool:
    return column.casefold() in _TIME_COLUMNS or all(
        isinstance(value, str) and bool(_DATE.fullmatch(value)) for value in values
    )
