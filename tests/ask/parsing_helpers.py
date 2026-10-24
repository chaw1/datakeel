# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Register explicit fixture subject types before exercising deterministic question parsing."""

from datakeel.ask.knowledge_parser import KnowledgeQuestion, parse_knowledge_question
from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot
from datakeel.core.link_models import LinkContext
from datakeel.core.metric_models import Measure, MetricDefinition, MetricTime, SemanticLayer
from datakeel.core.models import AssetRef, JsonDocument
from tests.ask.knowledge_helpers import entity

_METRICS = {
    "出货额",
    "库存量",
    "零售额",
    "出货量",
    "退款额",
    "维修费用",
    "销售总额",
    "customer_count",
    "revenue metric",
    "inventory_units",
    "retention",
}
_TABLES = {"orders", "orders 表", "sales table", "sales", "inventory", "crm/main/sales"}
_VIEWS = {"sales_summary"}
_OWNERS = {"供应链负责人", "负责人"}
_PEOPLE = {"周岩", "priya natarajan", "morgan"}
_TEAMS = {"finance team", "orders 团队", "operations team", "ops crew"}
_DATASETS = {"库存摘要", "出货额日报", "季度库存摘要"}


def registered_question(question: str, subject: str | None = None) -> KnowledgeQuestion | None:
    """Register a typed fixture identity, without providing an expected intent to production."""
    catalog, layer, context = registered_context(subject)
    return parse_knowledge_question(question, catalog, layer, context)


def registered_context(
    subject: str | None,
) -> tuple[CatalogSnapshot, SemanticLayer, LinkContext]:
    """Build isolated catalog or graph identities from the explicitly declared fixture types."""
    empty = CatalogSnapshot(scope="parser-fixture"), SemanticLayer(), LinkContext()
    if subject is None:
        return empty
    name = subject.casefold()
    if name in _METRICS:
        metric = MetricDefinition(
            id="fixture-metric",
            name=subject,
            description="Synthetic measure",
            owner="Fixture role",
            measure=Measure(table="fixture/table", column="value", aggregation="sum"),
            time=MetricTime(column="day"),
        )
        catalog = CatalogSnapshot(
            scope="parser-fixture",
            objects=(
                CatalogObject(
                    asset_ref=AssetRef(asset_type="metric", asset_id=metric.id), name=subject
                ),
            ),
        )
        return catalog, SemanticLayer(metrics=[metric]), LinkContext()
    if name in _TABLES | _VIEWS | _OWNERS:
        kind = "owner" if name in _OWNERS else "table"
        item = CatalogObject(
            asset_ref=AssetRef(asset_type=kind, asset_id="fixture-subject"),
            name=subject,
            properties=JsonDocument({"is_view": name in _VIEWS}),
        )
        return empty[0].model_copy(update={"objects": (item,)}), empty[1], empty[2]
    kind = "person" if name in _PEOPLE else "organization" if name in _TEAMS else "dataset"
    if name not in _PEOPLE | _TEAMS | _DATASETS:
        msg = f"Fixture subject type was not declared: {subject}"
        raise ValueError(msg)
    return empty[0], empty[1], LinkContext(entities=(entity("fixture-entity", subject, kind),))
