# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep natural requests distinct from metadata background and scalar metric heads."""

import pytest

from datakeel.ask.knowledge_parser import parse_knowledge_question
from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot
from datakeel.core.knowledge_models import KnowledgeIntent
from datakeel.core.metric_models import Measure, MetricDefinition, MetricTime, SemanticLayer
from datakeel.core.models import AssetRef, JsonDocument


def _context() -> tuple[CatalogSnapshot, SemanticLayer]:
    metric = MetricDefinition(
        id="parcel_total",
        name="parcel_total",
        synonyms=["total number of parcels"],
        description="Synthetic parcel count",
        owner="Fixture team",
        measure=Measure(table="parcels", column="value", aggregation="sum"),
        time=MetricTime(column="day"),
    )
    objects = (
        CatalogObject(
            asset_ref=AssetRef(asset_type="table", asset_id="parcels"), name="skylark_parcels"
        ),
        CatalogObject(
            asset_ref=AssetRef(asset_type="table", asset_id="rollup"),
            name="skylark_rollup",
            properties=JsonDocument({"is_view": True}),
        ),
        CatalogObject(
            asset_ref=AssetRef(asset_type="metric", asset_id=metric.id), name=metric.name
        ),
    )
    return CatalogSnapshot(scope="natural-boundaries", objects=objects), SemanticLayer(
        metrics=[metric]
    )


@pytest.mark.parametrize(
    ("question", "intent", "subject_id"),
    [
        ("和 skylark_parcels 有关的报表\uff0c能列一下吗\uff1f", "downstream", "parcels"),
        ("skylark_rollup 相关的指标\uff0c麻烦列出来。", "downstream", "rollup"),
        ("谁在读 skylark_parcels\uff1f", "downstream", "parcels"),
        ("谁在用 skylark_parcels\uff1f", "downstream", "parcels"),
        ("skylark_rollup 是谁在读\uff1f", "downstream", "rollup"),
        ("skylark_rollup 是谁在负责\uff1f", "owner", "rollup"),
        ("What is built on top of skylark_parcels?", "downstream", "parcels"),
        ("What is the impact of changing skylark_parcels?", "downstream", "parcels"),
        ("What is the impact of skylark_parcels?", "downstream", "parcels"),
        ("What would affect skylark_parcels?", "upstream", "parcels"),
        ("Which assets would be affected if skylark_rollup changed?", "downstream", "rollup"),
        ("Changes to which assets would affect skylark_rollup?", "upstream", "rollup"),
        ("如果 skylark_rollup 变了\uff0c哪些指标会受影响\uff1f", "downstream", "rollup"),
        ("What is total parcel_total's owner?", "owner", "parcel_total"),
        ("What is total parcel_total's source?", "upstream", "parcel_total"),
        ("What is total parcel_total's formula?", "upstream", "parcel_total"),
        ("What is the source of parcel_total?", "upstream", "parcel_total"),
        ("What is the formula of parcel_total?", "upstream", "parcel_total"),
        ("What is the owner of parcel_total?", "owner", "parcel_total"),
        ("What is the source of the total number of parcels?", "upstream", "parcel_total"),
        ("What is the total number of metrics using skylark_parcels?", "downstream", "parcels"),
        ("Tell me the number of tables used by skylark_rollup.", "upstream", "rollup"),
    ],
)
def test_natural_relation_keeps_intent_and_subject(
    question: str, intent: KnowledgeIntent, subject_id: str
) -> None:
    """Keep structural roles and ownership distinct in ordinary requests."""
    catalog, layer = _context()
    parsed = parse_knowledge_question(question, catalog, layer)
    assert parsed is not None
    assert parsed.intent == intent
    assert not parsed.unsupported_phrasing
    assert tuple(item.asset_ref.asset_id for item in parsed.candidates) == (subject_id,)


@pytest.mark.parametrize(
    "question",
    [
        "What is the total number of parcels?",
        "What was parcel_total last month?",
        "What is parcel_total this month?",
        "What was the total number of parcels last month?",
        "What is the value of parcel_total?",
        "What is total parcel_total last month?",
        "What is the value of parcel_total for each source?",
        "What is the total value of parcel_total for each owner?",
        "Show the top 5 depots by parcel_total.",
        "和 skylark_parcels 有关的报表里\uff0cparcel_total 的值是多少\uff1f",
        "The reports are based on skylark_parcels. What is the value of parcel_total?",
    ],
)
def test_scalar_metric_head_keeps_metric_route(question: str) -> None:
    """Recognize scalar or dated metric predicates after alias masking."""
    catalog, layer = _context()
    assert parse_knowledge_question(question, catalog, layer) is None


@pytest.mark.parametrize(
    "question",
    [
        "What is parcel_total?",
        "What is the purpose of parcel_total?",
        "Which tables are related to skylark_parcels?",
    ],
)
def test_unknown_relation_preserves_clarification(question: str) -> None:
    """Do not turn an unknown relation or a timeless definition into a value."""
    catalog, layer = _context()
    parsed = parse_knowledge_question(question, catalog, layer)
    assert parsed is not None
    assert parsed.unsupported_phrasing
