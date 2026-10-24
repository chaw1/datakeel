# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Prove complete-name association rules without substring or underscore heuristics."""

from pathlib import Path

import pytest

from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot
from datakeel.core.kg_product import KGEntity
from datakeel.core.link_matching import catalog_identifiers, catalog_names, match_entity
from datakeel.core.metric_models import TermDefinition, TermTarget
from datakeel.core.models import AssetRef
from datakeel.metrics.loader import load_layer
from datakeel.metrics.projection import build_snapshot


def _entity(name: str, entity_type: str = "dataset") -> KGEntity:
    return KGEntity(
        asset_ref=AssetRef(asset_type="kg_entity", asset_id=name, version="v1"),
        name=name,
        type=entity_type,
    )


def _tables(*names: str) -> CatalogSnapshot:
    return CatalogSnapshot(
        scope="fixture",
        objects=tuple(
            CatalogObject(
                asset_ref=AssetRef(asset_type="table", asset_id=f"example/main/{name}"),
                name=name,
                schema_name="main",
            )
            for name in names
        ),
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("sales table", ("sales",)),
        ("THE SALES TABLES", ("sales",)),
        ("main.sales", ("sales",)),
        ("example/main/sales", ("sales",)),
        ("erp_raw_sales", ()),
        ("sales_summary", ()),
        ("fct_sales", ()),
        ("orders_clean", ()),
        ("inventory_snapshot", ()),
    ],
)
def test_identifiers_match_whole_names_and_never_split_underscores(
    name: str, expected: tuple[str, ...]
) -> None:
    """The dangerous catalog-looking suffixes do not identify different tables."""
    matches = match_entity(_entity(name), (), _tables("sales", "orders", "inventory"))
    assert tuple(match.target.name for match in matches) == expected


def test_mention_spelling_and_duplicate_table_names_preserve_ambiguity() -> None:
    """Only supplied mention text participates, and equal table names keep both identities."""
    first = _tables("sales").objects[0]
    second = first.model_copy(
        update={"asset_ref": AssetRef(asset_type="table", asset_id="another/main/sales")}
    )
    catalog = CatalogSnapshot(scope="fixture", objects=(first, second))
    assert len(match_entity(_entity("daily fact"), ("sales",), catalog)) == 2
    assert match_entity(_entity("sales", "person"), (), catalog) == ()
    assert catalog_identifiers("The SALES, crm.sales, example/main/sales and 表 tables") == (
        "sales",
        "crm.sales",
        "example/main/sales",
        "and",
    )
    assert catalog_names(first.model_copy(update={"schema_name": None})) == (
        "sales",
        "example/main/sales",
    )


def test_metric_matching_uses_whole_names_suffixes_and_only_the_strongest_tier() -> None:
    """Identifiers, glossary names, synonyms and NFKC each retain exact priority."""
    layer = load_layer(Path("contracts/semantic-layer"))
    catalog = build_snapshot(layer, CatalogSnapshot(scope="empty"))
    assert len(match_entity(_entity("营业额", "metric"), (), catalog)) == 2
    for spelling in (
        "出货额指标",
        " 出货额 metric ",
        "shipment_amount",
        "".join(chr(ord(character) + 0xFEE0) for character in "shipment_amount"),
    ):
        result = match_entity(_entity(spelling, "metric"), (), catalog)
        assert len(result) == 1
        assert result[0].target.name == "出货额"
    assert match_entity(_entity("去年出货额", "metric"), (), catalog) == ()
    assert match_entity(_entity("出货", "metric"), (), catalog) == ()
    result = match_entity(_entity("营业额", "metric"), ("出货额",), catalog)
    assert [match.target.name for match in result] == ["出货额"]
    with_terms = layer.model_copy(
        update={
            "terms": [
                *layer.terms,
                TermDefinition(
                    term="Monthly turnover",
                    synonyms=["Monthly business"],
                    means=TermTarget(kind="metric", id="shipment_amount"),
                ),
            ]
        }
    )
    catalog = build_snapshot(with_terms, CatalogSnapshot(scope="empty"))
    assert match_entity(_entity("MONTHLY TURNOVER", "metric"), (), catalog)[0].strength == "exact"
    assert match_entity(_entity("Monthly business", "metric"), (), catalog)[0].strength == "synonym"


def test_optional_entity_suffix_does_not_shorten_registered_metric_vocabulary() -> None:
    """Catalog identifiers, names and glossary spellings retain their literal full names."""
    layer = load_layer(Path("contracts/semantic-layer"))
    metric = layer.metrics[0].model_copy(
        update={"id": "geometric", "name": "质量指标", "synonyms": ["shape metric"]}
    )
    layer = layer.model_copy(
        update={
            "metrics": [metric],
            "terms": [
                TermDefinition(
                    term="Geometry metric",
                    synonyms=["formal metric"],
                    means=TermTarget(kind="metric", id="geometric"),
                )
            ],
        }
    )
    catalog = build_snapshot(layer, CatalogSnapshot(scope="empty"))
    for shorter in ("geo", "质量", "shape", "geometry", "formal"):
        assert match_entity(_entity(shorter, "metric"), (), catalog) == ()
    for spelling in (
        "geometric",
        "geometric metric",
        "geometric指标",
        "质量指标",
        "质量指标 metric",
        "shape metric",
        "shape metric metric",
        "Geometry metric",
        "formal metric",
    ):
        matches = match_entity(_entity(spelling, "metric"), (), catalog)
        assert len(matches) == 1
        assert matches[0].target.asset_ref.asset_id == "geometric"
    assert match_entity(_entity("geometric", "metric"), (), catalog)[0].strength == "exact"
    assert match_entity(_entity("shape metric", "metric"), (), catalog)[0].strength == "synonym"
