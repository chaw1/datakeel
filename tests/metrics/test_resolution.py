# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Broken catalog references remain visible as unresolved metric cards."""

from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.metric_models import MetricDefinition, MetricFilter, SemanticLayer
from datakeel.metrics.resolution import resolve_metric


def test_resolve_metric_registered_fields_are_resolved(
    layer: SemanticLayer,
    catalog: CatalogSnapshot,
) -> None:
    """Resolve the complete declared field and dimension dependency set."""
    card = resolve_metric(layer.metrics[0], layer, [item.asset_ref for item in catalog.objects])
    assert (card.status, card.reasons) == ("resolved", [])


def test_resolve_metric_reports_missing_dimension_and_foreign_field(
    layer: SemanticLayer,
) -> None:
    """Report each actionable reference failure while preserving the definition."""
    metric = MetricDefinition.model_validate(
        {
            **layer.metrics[0].model_dump(),
            "dimensions": ["absent"],
            "filters": [MetricFilter(column="other/main/table/field", value=1).model_dump()],
        }
    )
    card = resolve_metric(metric, layer, [])
    assert card.status == "unresolved"
    assert "Unknown dimension: absent" in card.reasons
    assert "Column is outside measure table: other/main/table/field" in card.reasons
    assert "Missing column: test/main/orders/amount" in card.reasons


def test_resolve_metric_missing_time_field_is_unresolved(layer: SemanticLayer) -> None:
    """Every metric requires a registered temporal field."""
    card = resolve_metric(layer.metrics[0], layer, [])
    assert "Missing column: test/main/orders/date" in card.reasons
