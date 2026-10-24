# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exact subject tiers retain catalog identity and distinguish cross-document entities."""

import pytest

from datakeel.ask.knowledge_parser import parse_knowledge_question
from datakeel.ask.knowledge_subjects import subject_candidates, subject_suggestions
from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot
from datakeel.core.link_models import EntityLink, LinkEntitySource
from datakeel.core.metric_models import SemanticLayer
from datakeel.core.models import AssetRef
from datakeel.metrics.projection import build_snapshot
from tests.ask.knowledge_helpers import assertion, entity


def test_unlinked_whole_graph_names_remain_candidates_beside_catalog_names(
    layer: SemanticLayer,
) -> None:
    """A whole graph name is distinct until a current link identifies the same catalog asset."""
    catalog = build_snapshot(layer, CatalogSnapshot(scope="empty"))
    duplicates = (
        entity("first", "customer_count", "metric"),
        entity("second", "customer_count", "metric"),
    )
    found = subject_candidates("customer_count", catalog, layer, duplicates)
    assert len(found) == 3
    assert found[0].kind == "metric"
    target = next(item for item in catalog.objects if item.asset_ref.asset_id == "customer_count")
    links = tuple(
        EntityLink(
            assertion=assertion(
                item.asset_ref.asset_id, item.asset_ref, "link.maps_to", target.asset_ref
            ),
            entity=item,
            target=target,
            match_kind="unique",
            basis=("exact name",),
        )
        for item in duplicates
    )
    linked = subject_candidates("customer_count", catalog, layer, duplicates, links=links)
    assert linked == found[:1]
    ambiguous = subject_candidates("营业额", catalog, layer, ())
    assert {item.name for item in ambiguous} == {"销售额", "零售额"}
    roles = subject_candidates(
        "供应链负责人", catalog, layer, (entity("person", "供应链负责人", "person"),)
    )
    assert len(roles) == 2
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
    sources = tuple(
        LinkEntitySource(
            entity_id=item.asset_ref.asset_id,
            dataset_id=f"dataset-{index}",
            dataset_name=f"Notes {index}",
        )
        for index, item in enumerate(entities)
    )
    candidates = subject_candidates(
        "\uff2dorgan   Smith", catalog, layer, entities, entity_sources=sources
    )
    assert len(candidates) == 2
    assert all(item.kind == "kg_entity" for item in candidates)
    assert [item.dataset_name for item in candidates] == ["Notes 0", "Notes 1"]
    assert [item.dataset_id for item in candidates] == ["dataset-0", "dataset-1"]
    assert all(item.entity_type == "person" for item in candidates)
    assert subject_candidates("Morgan", catalog, layer, entities) == ()
    assert subject_suggestions("Morgan", catalog, entities, entity_sources=sources) == candidates


def test_complete_graph_subjects_win_over_incidental_metric_or_table_tokens(
    layer: SemanticLayer,
) -> None:
    """Report and team names remain graph subjects when a catalog token is only part of them."""
    table = CatalogObject(
        asset_ref=AssetRef(asset_type="table", asset_id="source/main/orders"), name="orders"
    )
    catalog = build_snapshot(layer, CatalogSnapshot(scope="fixture", objects=(table,)))
    catalog = catalog.model_copy(update={"objects": (*catalog.objects, table)})
    entities = (
        entity("daily-report", "出货额日报", "dataset"),
        entity("orders-team", "orders 团队", "organization"),
    )
    for question, item in zip(("出货额日报从哪来", "orders 团队负责哪些"), entities, strict=True):
        parsed = parse_knowledge_question(question)
        assert parsed is not None
        candidates = subject_candidates(parsed.subject, catalog, layer, entities)
        assert len(candidates) == 1
        assert candidates[0].asset_ref == item.asset_ref
        assert candidates[0].kind == "kg_entity"


@pytest.mark.parametrize(
    ("question", "name", "kind"),
    [
        ("monthly_report来源于哪张表", "monthly_report", "dataset"),
        ("哪些表用到了monthly_report", "monthly_report", "dataset"),
        ("Ops Crew都负责哪些", "Ops Crew", "organization"),
    ],
)
def test_relation_boundaries_resolve_complete_graph_subjects(
    question: str, name: str, kind: str
) -> None:
    """Question particles must not leak into exact graph names after subject extraction."""
    parsed = parse_knowledge_question(question)
    assert parsed is not None
    item = entity("subject", name, kind)
    found = subject_candidates(
        parsed.subject, CatalogSnapshot(scope="empty"), SemanticLayer(), (item,)
    )
    assert len(found) == 1
    assert found[0].asset_ref == item.asset_ref


def test_rejected_or_unrelated_links_do_not_hide_whole_graph_names(layer: SemanticLayer) -> None:
    """Rejected and different-target links cannot collapse subject identity."""
    catalog = build_snapshot(layer, CatalogSnapshot(scope="empty"))
    graph = entity("metric-entity", "customer_count", "metric")
    target = next(item for item in catalog.objects if item.asset_ref.asset_id == "customer_count")
    link = EntityLink(
        assertion=assertion("link", graph.asset_ref, "link.maps_to", target.asset_ref),
        entity=graph,
        target=target,
        match_kind="unique",
        basis=("exact name",),
    )
    rejected = link.model_copy(
        update={"assertion": link.assertion.model_copy(update={"status": "rejected"})}
    )
    unrelated = link.model_copy(
        update={
            "target": target.model_copy(
                update={"asset_ref": AssetRef(asset_type="metric", asset_id="other")}
            )
        }
    )
    for unusable in (rejected, unrelated):
        assert len(subject_candidates(graph.name, catalog, layer, (graph,), links=(unusable,))) == 2
    ambiguous = link.model_copy(update={"match_kind": "ambiguous"})
    assert len(subject_candidates(graph.name, catalog, layer, (graph,), links=(ambiguous,))) == 1


def test_whole_catalog_subjects_win_over_incidental_metric_tokens(layer: SemanticLayer) -> None:
    """Every vocabulary tier participates before metric substring fallback is considered."""
    objects = (
        CatalogObject(
            asset_ref=AssetRef(asset_type="owner", asset_id="report-team"), name="出货额日报团队"
        ),
        CatalogObject(
            asset_ref=AssetRef(asset_type="table", asset_id="source/main/customer_count_daily"),
            name="customer_count_daily",
        ),
    )
    catalog = build_snapshot(layer, CatalogSnapshot(scope="fixture", objects=objects))
    catalog = catalog.model_copy(update={"objects": (*catalog.objects, *objects)})
    for item in objects:
        found = subject_candidates(f"the {item.name} table", catalog, layer, ())
        assert len(found) == 1
        assert found[0].asset_ref.asset_id == item.asset_ref.asset_id


def test_suggestions_are_bounded_and_never_resolve_the_subject(layer: SemanticLayer) -> None:
    """Similarity has a suggestion-only role and cannot turn an unknown name into a fact."""
    catalog = build_snapshot(layer, CatalogSnapshot(scope="empty"))
    assert subject_candidates("weather forecasts", catalog, layer, ()) == ()
    suggestions = subject_suggestions("weather forecasts", catalog, ())
    assert len(suggestions) == 3
    assert all(item.kind == "metric" for item in suggestions)


@pytest.mark.parametrize(
    ("text", "expected_id"),
    [
        ("请看出货额口径", "shipment_amount"),
        ("reference customer_count details", "customer_count"),
        ("关于 orders 的说明", "source/main/orders"),
    ],
)
def test_tier_scanning_remains_available_only_after_complete_names_fail(
    layer: SemanticLayer, text: str, expected_id: str
) -> None:
    """The complete-name pass does not remove the existing metric and identifier fallback."""
    table = CatalogObject(
        asset_ref=AssetRef(asset_type="table", asset_id="source/main/orders"), name="orders"
    )
    catalog = build_snapshot(layer, CatalogSnapshot(scope="empty"))
    catalog = catalog.model_copy(update={"objects": (*catalog.objects, table)})
    found = subject_candidates(text, catalog, layer, ())
    assert len(found) == 1
    assert found[0].asset_ref.asset_id == expected_id
