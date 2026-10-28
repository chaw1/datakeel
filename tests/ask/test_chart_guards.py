# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Unparameterized chart boundaries provide measured mutation targets."""

from datakeel.ask.charts import select_chart
from datakeel.core.metric_models import MetricDefinition, QueryResult, SemanticLayer


def _metric(layer: SemanticLayer) -> MetricDefinition:
    return next(item for item in layer.metrics if item.id == "retail_revenue")


def test_chart_category_limit_is_hard(layer: SemanticLayer) -> None:
    """Thirty-one categories require a table regardless of label length."""
    result = QueryResult(columns=["region", "value"], rows=[[str(i), i] for i in range(31)])
    assert select_chart(result, _metric(layer)).type == "table"


def test_chart_long_labels_are_horizontal(layer: SemanticLayer) -> None:
    """A single long category label must remain legible without vertical crowding."""
    result = QueryResult(columns=["region", "value"], rows=[["Long category name", 1]])
    assert select_chart(result, _metric(layer)).type == "horizontal_bar"


def test_chart_extra_dimensions_are_tabular(layer: SemanticLayer) -> None:
    """Three dimensions cannot be silently discarded to make a two-dimensional chart."""
    result = QueryResult(columns=["a", "b", "c", "value"], rows=[["x", "y", "z", 1]])
    assert select_chart(result, _metric(layer)).type == "table"
