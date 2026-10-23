# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Catalog projections preserve semantic dependencies and typed revision metadata."""

from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.metric_models import SemanticLayer
from datakeel.metrics.projection import build_snapshot, metric_cards, semantic_layer


def test_semantic_projection_round_trips_definitions_and_links(
    layer: SemanticLayer,
    catalog: CatalogSnapshot,
) -> None:
    """Metrics, owners, terms, dimensions, and dependency edges are replayable."""
    snapshot = build_snapshot(layer, catalog)
    assert semantic_layer(snapshot) == layer
    assert metric_cards(snapshot)[0].status == "resolved"
    assert {link.kind for link in snapshot.links} == {"measures", "sliced_by", "means", "owned_by"}


def test_semantic_projection_records_time_field_dependency(
    layer: SemanticLayer,
    catalog: CatalogSnapshot,
) -> None:
    """Every metric records its mandatory temporal dependency."""
    snapshot = build_snapshot(layer, catalog)
    assert any(link.target.asset_id.endswith("/date") for link in snapshot.links)
