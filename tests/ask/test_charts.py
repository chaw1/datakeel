# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Shape, formatting, and authoritative-row guarantees for deterministic charts."""

from datetime import UTC, datetime

import pytest

from datakeel.ask.charts import answer_chart, select_chart
from datakeel.core.ask_chart_models import ChartType
from datakeel.core.ask_models import AskAnswer
from datakeel.core.metric_models import Measure, MetricDefinition, MetricTime, QueryResult


@pytest.fixture
def metric() -> MetricDefinition:
    """Supply a generated contract with explicit units and display precision."""
    return MetricDefinition(
        id="revenue",
        name="Revenue",
        description="Generated revenue",
        owner="Operations",
        measure=Measure(
            table="demo/main/orders", column="demo/main/orders/amount", aggregation="sum"
        ),
        time=MetricTime(column="demo/main/orders/date"),
        unit="USD",
        number_format="integer",
    )


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (QueryResult(columns=["value"], rows=[[42]]), "scalar"),
        (QueryResult(columns=["month", "value"], rows=[["2026-01", 10], ["2026-02", 20]]), "line"),
        (QueryResult(columns=["period", "value"], rows=[["2026-Q1", 10]]), "line"),
        (QueryResult(columns=["region", "value"], rows=[["East", 10], ["West", 20]]), "bar"),
        (QueryResult(columns=["region", "value"], rows=[[str(i), i] for i in range(8)]), "bar"),
        (
            QueryResult(columns=["region", "value"], rows=[[str(i), i] for i in range(9)]),
            "horizontal_bar",
        ),
        (
            QueryResult(columns=["region", "value"], rows=[["Long category name", 10]]),
            "horizontal_bar",
        ),
        (
            QueryResult(columns=["region", "channel", "value"], rows=[["East", "Shop", 10]]),
            "grouped_bar",
        ),
        (QueryResult(columns=["a", "b", "c", "value"], rows=[["x", "y", "z", 10]]), "table"),
        (QueryResult(columns=["region", "value"], rows=[[str(i), i] for i in range(31)]), "table"),
        (
            QueryResult(columns=["region", "value"], rows=[[str(i), i] for i in range(30)]),
            "horizontal_bar",
        ),
        (QueryResult(columns=["region", "name"], rows=[["East", "Shop"]]), "table"),
        (QueryResult(columns=["region", "active"], rows=[["East", True]]), "table"),
        (QueryResult(columns=["value"], rows=[[None]]), "table"),
        (QueryResult(columns=["store", "value"], rows=[[2026, None]]), "table"),
        (QueryResult(columns=["value"], rows=[]), "table"),
        (QueryResult(columns=["value"], rows=[[1], [2]]), "table"),
        (QueryResult(columns=["region", "one", "two"], rows=[["East", 1, 2]]), "table"),
        (
            QueryResult(
                columns=["region", "channel", "value"],
                rows=[["East", str(i), i] for i in range(31)],
            ),
            "table",
        ),
    ],
)
def test_chart_shape_selects_documented_type(
    result: QueryResult, expected: ChartType, metric: MetricDefinition
) -> None:
    """Cover every public chart rule and both category boundaries."""
    chart = select_chart(result, metric)
    assert chart.type == expected
    assert expected in chart.available_types
    assert "table" in chart.available_types


def test_chart_references_unmodified_result_and_contract(metric: MetricDefinition) -> None:
    """Reference original columns, preserving order, nulls, negatives, and precision."""
    result = QueryResult(columns=["region", "value"], rows=[["West", -1.23456789], ["East", None]])
    before = result.model_dump_json()
    chart = select_chart(result, metric, question="Revenue share by region")
    assert chart.x == "region"
    assert chart.y == ("value",)
    assert chart.unit == "USD"
    assert chart.number_format == "integer"
    assert chart.sort == "source"
    assert chart.show_percent
    assert result.model_dump_json() == before
    assert "rows" not in chart.model_dump()


def test_numeric_dimension_is_preserved_and_two_dimensions_allow_stacking(
    metric: MetricDefinition,
) -> None:
    """Treat engine value as the measure even if category identifiers are numeric."""
    chart = select_chart(
        QueryResult(columns=["store", "channel", "value"], rows=[[1, "Shop", 10]]), metric
    )
    assert chart.x == "store"
    assert chart.series == "channel"
    assert chart.y == ("value",)
    assert chart.available_types == ("grouped_bar", "stacked_bar", "table")


def test_non_metric_answer_does_not_gain_a_chart() -> None:
    """Keep clarifications free of numeric presentation."""
    answer = AskAnswer(
        session_id="session",
        question="Which metric?",
        status="clarification",
        message="Clarify",
        reference_instant=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert answer_chart(answer) is answer
