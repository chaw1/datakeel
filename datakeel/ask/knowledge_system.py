# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Aggregate explicit column lineage and ownership into table-level system facts."""

from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.knowledge_models import (
    KnowledgeIntent,
    KnowledgeSubject,
    KnowledgeSystemRecord,
)
from datakeel.core.metric_models import SemanticLayer
from datakeel.core.models import AssetRef


def system_records(
    subject: KnowledgeSubject,
    intent: KnowledgeIntent,
    catalog: CatalogSnapshot,
    layer: SemanticLayer,
) -> tuple[tuple[KnowledgeSystemRecord, ...], str]:
    """Read registered facts without treating foreign keys or descriptive messages as facts."""
    identity = subject.asset_ref.asset_id
    targets: set[str] = set()
    if intent == "owner":
        targets = {
            link.target.asset_id
            for link in catalog.links
            if link.kind == "owned_by" and link.source.asset_id == identity
        }
    elif intent == "owned" and subject.kind == "owner":
        targets = {
            link.source.asset_id
            for link in catalog.links
            if link.kind == "owned_by"
            and link.target.asset_id == identity
            and link.source.asset_type == "metric"
        }
    elif intent == "upstream" and subject.kind == "metric":
        return _metric_upstream(subject, catalog, layer)
    elif intent in {"upstream", "downstream"} and subject.kind in {"table", "view"}:
        targets = _table_neighbors(subject, intent, catalog)
    records = tuple(
        KnowledgeSystemRecord(
            asset_ref=item.asset_ref.model_copy(update={"version": str(item.revision)})
            if item.asset_ref.version is None
            else item.asset_ref,
            name=item.name,
            relation=intent if intent != "related" else "upstream",
        )
        for item in catalog.objects
        if item.asset_ref.asset_id in targets
    )
    if records:
        return records, "系统登记的记录。"
    if intent == "owned" and subject.kind == "kg_entity":
        return (), "系统只登记了角色, 没有登记到人。"
    labels = {"owner": "负责人", "upstream": "上游", "downstream": "下游", "owned": "负责的资产"}
    return (), f"系统里没有登记{labels.get(intent, '相关知识')}。"


def _metric_upstream(
    subject: KnowledgeSubject, catalog: CatalogSnapshot, layer: SemanticLayer
) -> tuple[tuple[KnowledgeSystemRecord, ...], str]:
    metric = next((item for item in layer.metrics if item.id == subject.asset_ref.asset_id), None)
    if metric is None:
        return (), "系统里没有登记上游。"
    table = next(
        (item for item in catalog.objects if item.asset_ref.asset_id == metric.measure.table), None
    )
    if table is not None:
        ref = table.asset_ref.model_copy(update={"version": str(table.revision)})
        if table.asset_ref.version is not None:
            ref = table.asset_ref
        name, message = table.name, "系统登记的记录。"
    else:
        ref = AssetRef(
            asset_type="table",
            asset_id=metric.measure.table,
            version=f"semantic/{metric.id}/{metric.version}",
        )
        name = metric.measure.table
        message = "语义层登记了度量表引用。目录里尚未解析, 引用版本来自指标定义。"
    return (KnowledgeSystemRecord(asset_ref=ref, name=name, relation="upstream"),), message


def _table_neighbors(
    subject: KnowledgeSubject, intent: KnowledgeIntent, catalog: CatalogSnapshot
) -> set[str]:
    identity = subject.asset_ref.asset_id
    parents = {
        item.asset_ref.asset_id: item.table_id
        for item in catalog.objects
        if item.asset_ref.asset_type == "column"
    }
    for link in catalog.links:
        if link.kind == "contains" and link.source.asset_type == "table":
            parents[link.target.asset_id] = link.source.asset_id
    targets: set[str] = set()
    for link in catalog.links:
        if link.kind == "derived":
            near, far = (
                (link.target, link.source) if intent == "upstream" else (link.source, link.target)
            )
            if parents.get(near.asset_id) == identity:
                _add_parent(targets, parents, far, identity)
        if (
            intent == "downstream"
            and link.kind == "measures"
            and parents.get(link.target.asset_id) == identity
        ):
            targets.add(link.source.asset_id)
    return targets


def _add_parent(targets: set[str], parents: dict[str, str | None], ref: AssetRef, own: str) -> None:
    parent = parents.get(ref.asset_id)
    if parent and parent != own:
        targets.add(parent)
