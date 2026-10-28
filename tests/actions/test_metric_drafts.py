# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Imported metric semantics remain inert until a signed human confirmation."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan, prepare_action
from datakeel.catalog.metadata_service import import_dbt
from datakeel.catalog.service import import_catalog
from datakeel.core.catalog_models import CatalogImportRequest, CatalogObject, CatalogSnapshot
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError, ValidationError
from datakeel.core.metadata_imports import DbtImportRequest, MetadataImportBatch, MetricDraft
from datakeel.core.metric_models import Measure, MetricDefinition, MetricTime
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.storage.catalog_queries import get_object
from datakeel.storage.metadata_store import publish_metadata
from datakeel.storage.metric_store import list_metrics

if TYPE_CHECKING:
    from datakeel.storage.database import Database

_DBT_FIXTURES = Path(__file__).parents[1] / "fixtures" / "dbt"


@pytest.fixture
def source_request(tmp_path: Path) -> CatalogImportRequest:
    """Build an isolated physical table for approving generated semantic definitions."""
    path = tmp_path / "draft-source.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sales(amount REAL, day DATE)")
    return CatalogImportRequest(
        source_id="sample", name="Sample", connection_url=f"sqlite:///{path}"
    )


def _definition() -> MetricDefinition:
    return MetricDefinition(
        id="sales_total",
        name="Sales total",
        description="Generated total sales",
        owner="owner@example.org",
        measure=Measure(
            table="sample/main/sales", column="sample/main/sales/amount", aggregation="sum"
        ),
        time=MetricTime(column="sample/main/sales/day"),
    )


def _draft(db: Database, definition: MetricDefinition | None = None) -> MetadataImportBatch:
    draft = MetricDraft(
        unique_id="metric.shop.sales",
        raw=JsonDocument({"name": "sales", "type": "simple"}),
        definition=definition,
    )
    item = CatalogObject(
        asset_ref=AssetRef(asset_type="metric_draft", asset_id="dbt/draft/sales"),
        name="Sales draft",
        source_id="sample",
        properties=JsonDocument(draft.model_dump(mode="json")),
    )
    batch = MetadataImportBatch(
        snapshot=CatalogSnapshot(scope="metadata:dbt:sample", objects=(item,))
    )
    publish_metadata(db, batch)
    return batch


def test_metric_draft_when_unapproved_cannot_enter_semantic_layer(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """Preparation and missing approval never install an imported metric."""
    import_catalog(db, source_request)
    _draft(db, _definition())
    assert not list_metrics(db)
    plan = prepare_action(db, "confirm_metric_draft", JsonDocument({"draft_id": "dbt/draft/sales"}))
    assert plan.requires_approval
    assert not list_metrics(db)
    with pytest.raises(AuthorizationError, match="approval"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert not list_metrics(db)


def test_metric_draft_when_approved_installs_once_and_reimport_keeps_decision(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """A signed frozen plan publishes semantics once and unchanged artifacts keep approval."""
    import_catalog(db, source_request)
    batch = _draft(db)
    params = JsonDocument(
        {"draft_id": "dbt/draft/sales", "definition": _definition().model_dump(mode="json")}
    )
    plan = prepare_action(db, "confirm_metric_draft", params)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    request = ExecuteRequest(plan_digest=plan.plan_digest, operation_id=plan.operation_id)
    first = execute_plan(db, plan.id, request)
    assert first.status == "SUCCEEDED"
    assert execute_plan(db, plan.id, request).id == first.id
    assert [card.definition.id for card in list_metrics(db)] == ["sales_total"]
    assert get_object(db, "dbt/draft/sales").properties.root["status"] == "confirmed"
    assert publish_metadata(db, batch).event_id is None
    with pytest.raises(ConflictError, match="already confirmed"):
        prepare_action(db, "confirm_metric_draft", params)


def test_metric_draft_when_incomplete_deleted_or_missing_rejects_before_plan(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """Incomplete draft proposals require human input and deleted sources cannot be approved."""
    import_catalog(db, source_request)
    batch = _draft(db)
    params = JsonDocument({"draft_id": "dbt/draft/sales"})
    with pytest.raises(ValidationError, match="complete definition"):
        prepare_action(db, "confirm_metric_draft", params)
    publish_metadata(db, MetadataImportBatch(snapshot=CatalogSnapshot(scope=batch.snapshot.scope)))
    with pytest.raises(ConflictError, match="deleted"):
        prepare_action(db, "confirm_metric_draft", params)
    with pytest.raises(NotFoundError, match="not found"):
        prepare_action(db, "confirm_metric_draft", JsonDocument({"draft_id": "absent"}))


def test_metric_draft_when_source_changes_invalidates_frozen_plan(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """Approval cannot authorize a source version that changed after review."""
    import_catalog(db, source_request)
    batch = _draft(db, _definition())
    plan = prepare_action(db, "confirm_metric_draft", JsonDocument({"draft_id": "dbt/draft/sales"}))
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    publish_metadata(db, MetadataImportBatch(snapshot=CatalogSnapshot(scope=batch.snapshot.scope)))
    with pytest.raises(ConflictError, match="target state changed"):
        execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert not list_metrics(db)


def test_metric_draft_when_updated_requires_new_confirmation_and_checks_version(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """Changed imported semantics require another approval and record a new metric version."""
    import_catalog(db, source_request)
    batch = _draft(db, _definition())
    params = JsonDocument({"draft_id": "dbt/draft/sales"})
    plan = prepare_action(db, "confirm_metric_draft", params)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    item = batch.snapshot.objects[0]
    draft = MetricDraft.model_validate(item.properties.root).model_copy(
        update={"raw": JsonDocument({"name": "sales", "description": "Updated draft"})}
    )
    updated = item.model_copy(update={"properties": JsonDocument(draft.model_dump(mode="json"))})
    publish_metadata(
        db,
        batch.model_copy(
            update={"snapshot": batch.snapshot.model_copy(update={"objects": (updated,)})}
        ),
    )
    assert list_metrics(db)[0].definition.version == 1
    bad = JsonDocument(
        {
            "draft_id": "dbt/draft/sales",
            "definition": _definition().model_copy(update={"version": 99}).model_dump(mode="json"),
        }
    )
    with pytest.raises(ConflictError, match="expected version"):
        prepare_action(db, "confirm_metric_draft", bad)
    plan = prepare_action(db, "confirm_metric_draft", params)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    assert list_metrics(db)[0].definition.version == 2
    confirmed = MetricDraft.model_validate(get_object(db, "dbt/draft/sales").properties.root)
    assert confirmed.definition is not None
    assert confirmed.definition.version == 2


def test_metric_draft_when_id_belongs_to_table_rejects_before_preparing_plan(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """A metric cannot replace a physical table by reusing its global catalog identity."""
    import_catalog(db, source_request)
    _draft(db, _definition().model_copy(update={"id": "sample/main/sales"}))
    with pytest.raises(ValidationError, match="another catalog object type"):
        prepare_action(db, "confirm_metric_draft", JsonDocument({"draft_id": "dbt/draft/sales"}))
    assert not list_metrics(db)
    assert get_object(db, "sample/main/sales").asset_ref.asset_type == "table"


def test_metric_draft_when_dependency_fingerprint_changes_resets_confirmation(
    db: Database, source_request: CatalogImportRequest
) -> None:
    """A changed upstream measure revokes the imported proposal's prior approval."""
    import_catalog(db, source_request)
    batch = _draft(db, _definition())
    params = JsonDocument({"draft_id": "dbt/draft/sales"})
    plan = prepare_action(db, "confirm_metric_draft", params)
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    item = batch.snapshot.objects[0]
    draft = MetricDraft.model_validate(item.properties.root).model_copy(
        update={
            "source_fingerprint": "new-upstream-measure",
            "definition": _definition().model_copy(update={"owner": "New owner"}),
        }
    )
    updated = item.model_copy(update={"properties": JsonDocument(draft.model_dump(mode="json"))})
    publish_metadata(
        db,
        batch.model_copy(
            update={"snapshot": batch.snapshot.model_copy(update={"objects": (updated,)})}
        ),
    )
    saved = MetricDraft.model_validate(get_object(db, "dbt/draft/sales").properties.root)
    assert saved.status == "draft"
    assert saved.definition is not None
    assert saved.definition.owner == "New owner"
    assert list_metrics(db)[0].definition.owner != "New owner"
    assert prepare_action(db, "confirm_metric_draft", params).requires_approval


def _fixture_request(manifest: JsonDocument) -> DbtImportRequest:
    return DbtImportRequest(
        source_id="shop",
        manifest=manifest,
        catalog=JsonDocument.model_validate_json((_DBT_FIXTURES / "catalog.json").read_text()),
    )


def _reparsed(manifest: JsonDocument) -> JsonDocument:
    """Simulate a fresh dbt parse: new parse timestamps and a different target path."""
    root = dict(manifest.root)
    for collection in ("nodes", "sources", "exposures", "metrics", "semantic_models"):
        resources = root.get(collection)
        if isinstance(resources, dict):
            root[collection] = {
                key: {**value, "created_at": 1.9e9, "compiled_path": f"ci-target/{key}.sql"}
                if isinstance(value, dict)
                else value
                for key, value in resources.items()
            }
    return JsonDocument(root)


def test_metric_draft_when_dbt_reparses_unchanged_project_keeps_confirmation(
    db: Database,
) -> None:
    """Parse bookkeeping is not metadata: approval survives and nothing is reported changed."""
    manifest = JsonDocument.model_validate_json((_DBT_FIXTURES / "manifest.json").read_text())
    first = import_dbt(db, _fixture_request(manifest))
    draft_id = "shop/dbt-draft/metric.p22_shop.total_revenue"
    plan = prepare_action(db, "confirm_metric_draft", JsonDocument({"draft_id": draft_id}))
    approve_plan(db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest))
    execute_plan(db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest))
    again = import_dbt(db, _fixture_request(_reparsed(manifest)))
    assert get_object(db, draft_id).properties.root["status"] == "confirmed"
    assert again.changed == 0
    assert again.unchanged == first.new
    assert again.event_id is None
