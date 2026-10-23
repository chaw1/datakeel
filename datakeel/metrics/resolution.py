# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicitly resolve every metric dependency against registered catalog assets."""

from datakeel.core.metric_models import MetricCard, MetricDefinition, SemanticLayer
from datakeel.core.models import AssetRef


def resolve_metric(
    metric: MetricDefinition, layer: SemanticLayer, assets: list[AssetRef]
) -> MetricCard:
    """Retain broken metric definitions with actionable missing-reference reasons."""
    registered = {(item.asset_type, item.asset_id) for item in assets}
    references = [("table", metric.measure.table), ("column", metric.measure.column)]
    references.extend(("column", item.column) for item in metric.filters)
    references.append(("column", metric.time.column))
    dimensions = {item.id: item for item in layer.dimensions}
    reasons: list[str] = []
    for identity in metric.dimensions:
        if identity not in dimensions:
            reasons.append(f"Unknown dimension: {identity}")
        else:
            references.append(("column", dimensions[identity].column))
    reasons.extend(
        f"Missing {kind}: {identity}"
        for kind, identity in references
        if (kind, identity) not in registered
    )
    for kind, identity in references:
        if kind == "column" and identity.rsplit("/", 1)[0] != metric.measure.table:
            reasons.append(f"Column is outside measure table: {identity}")
    return MetricCard(
        definition=metric,
        status="unresolved" if reasons else "resolved",
        reasons=sorted(set(reasons)),
    )
