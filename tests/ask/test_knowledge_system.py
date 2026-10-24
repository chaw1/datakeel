# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Registered column derivation, semantic ownership and measures define system records."""

from datakeel.ask.knowledge_claims import document_claims
from datakeel.ask.knowledge_subjects import catalog_subject, entity_subject
from datakeel.ask.knowledge_system import system_records
from datakeel.core.catalog_models import CatalogLink, CatalogObject, CatalogSnapshot
from datakeel.core.knowledge_models import KnowledgeSubject
from datakeel.core.metric_models import SemanticLayer
from datakeel.core.models import AssetRef
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.catalog_store import read_snapshot
from datakeel.storage.database import Database
from tests.ask.knowledge_helpers import claim_context, entity, source_reader


def test_registered_lineage_excludes_foreign_keys_and_aggregates_columns(
    db: Database,
    enterprise_sample: EnterpriseSample,
    layer: SemanticLayer,
) -> None:
    """Table-level upstream and downstream follow columns and measures, not foreign keys."""
    with db.session() as session:
        snapshot = read_snapshot(session)
    subjects = {
        item.asset_ref.asset_id: catalog_subject(item)
        for item in snapshot.objects
        if item.asset_ref.asset_type in {"table", "metric", "owner"}
    }
    records, _ = system_records(subjects["erp/main/shipments"], "upstream", snapshot, layer)
    assert records == ()
    records, _ = system_records(subjects["ecommerce/main/orders"], "downstream", snapshot, layer)
    assert {item.asset_ref.asset_id for item in records} == {
        "ecommerce/main/retail_summary",
        "retail_revenue",
        "order_count",
        "retail_units",
    }
    records, _ = system_records(subjects["crm/main/sales_summary"], "upstream", snapshot, layer)
    assert {item.asset_ref.asset_id for item in records} == {"crm/main/sales"}
    assert subjects["crm/main/sales_summary"].kind == "view"
    records, _ = system_records(subjects["owner/供应链负责人"], "owned", snapshot, layer)
    assert {item.asset_ref.asset_id for item in records} == {"shipment_amount", "shipment_units"}
    records, message = system_records(
        entity_subject(entity("person", "Morgan", "person")), "owned", snapshot, layer
    )
    assert records == ()
    assert "系统只登记了角色" in message


def test_table_ownership_reads_registered_owned_by_instead_of_always_reporting_missing() -> None:
    """Explicit table ownership is a system fact even when no graph exists."""
    table = CatalogObject(
        asset_ref=AssetRef(asset_type="table", asset_id="sample/main/orders"), name="orders"
    )
    owner = CatalogObject(
        asset_ref=AssetRef(asset_type="owner", asset_id="owner/operations"), name="Operations"
    )
    snapshot = CatalogSnapshot(
        scope="owned",
        objects=(table, owner),
        links=(CatalogLink(source=table.asset_ref, target=owner.asset_ref, kind="owned_by"),),
    )
    records, _ = system_records(catalog_subject(table), "owner", snapshot, SemanticLayer())
    assert len(records) == 1
    assert records[0].name == "Operations"


def test_unresolved_metric_retains_declared_measure_table_with_semantic_revision(
    layer: SemanticLayer,
) -> None:
    """Missing catalog imports cannot erase a registered metric's declared upstream."""
    definition = layer.metrics[0].model_copy(update={"version": 7})
    declaration = layer.model_copy(update={"metrics": [definition]})
    subject = KnowledgeSubject(
        asset_ref=AssetRef(asset_type="metric", asset_id=definition.id, version="7"),
        name=definition.name,
        kind="metric",
    )
    records, message = system_records(
        subject, "upstream", CatalogSnapshot(scope="empty"), declaration
    )
    assert len(records) == 1
    assert records[0].asset_ref.asset_id == definition.measure.table
    assert records[0].asset_ref.asset_type == "table"
    assert records[0].asset_ref.version == f"semantic/{definition.id}/7"
    assert records[0].name == definition.measure.table
    assert "目录里尚未解析" in message
    assert "指标定义" in message


def test_semantic_table_reference_does_not_invent_a_graph_association() -> None:
    """A declared table with no graph link still has the not-in-catalog consistency state."""
    subject, context = claim_context()
    declared_table = context.links[1].target.asset_ref.asset_id
    context = context.model_copy(update={"links": context.links[:1]})
    claims, _ = document_claims(subject, "upstream", context, {declared_table}, source_reader)
    assert claims[0].consistency == "not_in_catalog"
    assert claims[0].other_end.asset_ref is None
