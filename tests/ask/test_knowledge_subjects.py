# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exact subject tiers retain catalog identity and distinguish cross-document entities."""

from datakeel.ask.knowledge_subjects import subject_candidates, subject_suggestions
from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot
from datakeel.core.metric_models import SemanticLayer
from datakeel.core.models import AssetRef
from datakeel.metrics.projection import build_snapshot
from tests.ask.knowledge_helpers import entity


def test_metric_and_role_tiers_short_circuit_same_named_graph_entities(
    layer: SemanticLayer,
) -> None:
    """Graph duplicates cannot introduce ambiguity after a metric or registered role resolves."""
    catalog = build_snapshot(layer, CatalogSnapshot(scope="empty"))
    duplicates = (
        entity("first", "customer_count", "metric"),
        entity("second", "customer_count", "metric"),
    )
    found = subject_candidates("customer_count", catalog, layer, duplicates)
    assert len(found) == 1
    assert found[0].kind == "metric"
    ambiguous = subject_candidates("营业额", catalog, layer, ())
    assert {item.name for item in ambiguous} == {"销售额", "零售额"}
    roles = subject_candidates(
        "供应链负责人", catalog, layer, (entity("person", "供应链负责人", "person"),)
    )
    assert len(roles) == 1
    assert roles[0].kind == "owner"


def test_catalog_identifiers_do_not_split_underscores_and_keep_same_tier_ambiguity() -> None:
    """Whole identifiers preserve raw-table boundaries and duplicate names need clarification."""
    objects = tuple(
        CatalogObject(
            asset_ref=AssetRef(asset_type="table", asset_id=f"{source}/main/orders"),
            name="orders",
            schema_name="main",
        )
        for source in ("one", "two")
    )
    catalog = CatalogSnapshot(scope="test", objects=objects)
    layer = SemanticLayer()
    assert len(subject_candidates("orders table", catalog, layer, ())) == 2
    assert len(subject_candidates("MAIN.ORDERS", catalog, layer, ())) == 2
    found = subject_candidates("one/main/orders", catalog, layer, ())
    assert len(found) == 1
    assert found[0].asset_ref.asset_id == "one/main/orders"
    assert subject_candidates("orders_clean", catalog, layer, ()) == ()
    assert subject_candidates("fct_orders", catalog, layer, ()) == ()
    assert subject_candidates("the table", catalog, layer, ()) == ()


def test_graph_names_match_normalized_whole_names_and_keep_dataset_identity() -> None:
    """Equal graph names in independent datasets remain separate exact candidates."""
    entities = (
        entity("dataset-one-person", "Morgan Smith", "person"),
        entity("dataset-two-person", "Morgan Smith", "person"),
    )
    catalog, layer = CatalogSnapshot(scope="empty"), SemanticLayer()
    candidates = subject_candidates("\uff2dorgan   Smith", catalog, layer, entities)
    assert len(candidates) == 2
    assert all(item.kind == "kg_entity" for item in candidates)
    assert subject_candidates("Morgan", catalog, layer, entities) == ()
    assert subject_suggestions("Morgan", catalog, entities) == candidates


def test_suggestions_are_bounded_and_never_resolve_the_subject(layer: SemanticLayer) -> None:
    """Similarity has a suggestion-only role and cannot turn an unknown name into a fact."""
    catalog = build_snapshot(layer, CatalogSnapshot(scope="empty"))
    assert subject_candidates("weather forecasts", catalog, layer, ()) == ()
    suggestions = subject_suggestions("weather forecasts", catalog, ())
    assert len(suggestions) == 3
    assert all(item.kind == "metric" for item in suggestions)
