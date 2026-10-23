# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Dimension parsing is restricted to the resolved metric's supported slicing fields."""

from datakeel.ask.dimensions import parse_dimensions
from datakeel.core.metric_models import MetricCard, SemanticLayer


def test_dimension_values_are_scoped_to_selected_metric(layer: SemanticLayer) -> None:
    """Only retail dimensions are selected even though multiple sources reuse the same values."""
    card = MetricCard(
        definition=next(item for item in layer.metrics if item.id == "retail_revenue")
    )
    result = parse_dimensions("华东区线上零售额", card, layer)
    assert {item.dimension_id for item in result.slices} == {"retail_region", "retail_channel"}
    assert result.issues == ()
    assert all(item.match_kind == "dimension_value" for item in result.matches)


def test_dimension_names_and_glossary_aliases_can_request_grouping(layer: SemanticLayer) -> None:
    """Grouping through a registered dimension retains its semantic anchors."""
    card = MetricCard(
        definition=next(item for item in layer.metrics if item.id == "retail_revenue")
    )
    result = parse_dimensions("上个季度按零售区域和各渠道零售额", card, layer)
    assert result.group_by == ("retail_channel", "retail_region")
    assert result.issues == ()
    assert any(item.term_id == "term/零售区域" for item in result.matches)


def test_multiple_or_unknown_dimension_values_require_clarification(layer: SemanticLayer) -> None:
    """Conflicting or unregistered region slices cannot silently become unrestricted queries."""
    card = MetricCard(
        definition=next(item for item in layer.metrics if item.id == "retail_revenue")
    )
    assert parse_dimensions("华东和华南零售额", card, layer).issues
    assert parse_dimensions("东北区零售额", card, layer).issues
