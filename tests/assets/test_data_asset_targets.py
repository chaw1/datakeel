# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Real native ownership and version policies cannot be bypassed by alternate references."""

from datetime import UTC, datetime, timedelta

import pytest

from datakeel.assets.access import require_access
from datakeel.assets.service import get_asset_card
from datakeel.core.catalog_models import CatalogLink, CatalogObject, CatalogSnapshot
from datakeel.core.data_asset_models import (
    AccessContext,
    AssetApplicationInput,
    AssetMutationContext,
    AssetUsageQuery,
    DataAssetDefinition,
)
from datakeel.core.errors import AuthorizationError
from datakeel.core.evidence_models import Assertion, EvidenceAnchor, ExtractorRef
from datakeel.core.models import AssetRef, FileItem, JsonDocument, LineageEvent, new_id
from datakeel.storage.catalog_store import publish_snapshot_in_session
from datakeel.storage.data_asset_access import list_usage
from datakeel.storage.data_asset_grants import decide_application_in_session, submit_application
from datakeel.storage.data_asset_store import create_asset_in_session, set_status_in_session
from datakeel.storage.data_asset_targets import resolve_access_targets
from datakeel.storage.database import Database, DatasetRow, TaskRow, VersionRow
from datakeel.storage.events import append_event
from datakeel.storage.evidence_rows import AssertionRow

NOW = datetime(2030, 1, 1, tzinfo=UTC)
ACCESS = AccessContext(actor="reader", entry="mcp", scope="query")


def _context() -> AssetMutationContext:
    return AssetMutationContext(actor="owner", operation_id=new_id())


def _asset(db: Database, target: AssetRef) -> str:
    with db.session() as session:
        asset = create_asset_in_session(
            session,
            DataAssetDefinition(
                target=target,
                name="Generated protected resource",
                owner="Owner",
                classification="request",
            ),
            _context(),
        )
        set_status_in_session(session, asset.id, "published", _context())
        session.commit()
        return asset.id


def _grant(db: Database, asset_id: str) -> None:
    request = submit_application(
        db,
        AssetApplicationInput(
            asset_id=asset_id,
            purpose="Regression",
            scopes=("query",),
            expires_at=NOW + timedelta(days=1),
        ),
        "reader",
        now=NOW,
    )
    with db.session() as session:
        decide_application_in_session(session, request.id, _context(), approved=True, now=NOW)
        session.commit()


def _dataset(db: Database) -> None:
    file = FileItem(
        id="file",
        filename="fixture.txt",
        path="fixture.txt",
        size=2,
        sha256="fixture",
        modality="text",
    )
    with db.session() as session:
        session.add(
            DatasetRow(
                id="dataset",
                name="Generated",
                files=[file.model_dump()],
                metadata_values={"source_id": "source"},
            )
        )
        session.flush()
        for version in ("v1", "v2"):
            session.add(VersionRow(id=version, dataset_id="dataset", manifest=[file.model_dump()]))
        session.flush()
        session.add(
            TaskRow(
                id="task",
                dataset_id="dataset",
                input_version_id="v1",
                idempotency_key="generated-task",
            )
        )
        session.commit()


def test_versioned_native_files_and_tasks_require_only_their_version_policy(db: Database) -> None:
    """An exact old-version read stays allowed while a generic read checks every version."""
    _dataset(db)
    first = _asset(db, AssetRef(asset_id="dataset", version="v1"))
    second = _asset(db, AssetRef(asset_id="dataset", version="v2"))
    _grant(db, first)
    for target in (
        AssetRef(asset_type="file", asset_id="file", version="v1"),
        AssetRef(asset_type="version", asset_id="v1"),
        AssetRef(asset_type="task", asset_id="task"),
    ):
        result = require_access(db, (target,), ACCESS, now=NOW)
        assert [item.asset_id for item in result] == [first]
    for target in (
        AssetRef(asset_type="file", asset_id="file"),
        AssetRef(asset_type="file", asset_id="file", version="v2"),
        AssetRef(asset_id="dataset"),
        AssetRef(asset_type="resource", asset_id="dataset"),
    ):
        with pytest.raises(AuthorizationError):
            require_access(db, (target,), ACCESS, now=NOW)
    _grant(db, second)
    assert (
        len(require_access(db, (AssetRef(asset_type="file", asset_id="file"),), ACCESS, now=NOW))
        == 2
    )


def _catalog(db: Database) -> tuple[AssetRef, AssetRef]:
    table = AssetRef(asset_type="table", asset_id="source/main/orders")
    column = AssetRef(asset_type="column", asset_id="source/main/orders/amount")
    metric = AssetRef(asset_type="metric", asset_id="revenue", version="1")
    snapshot = CatalogSnapshot(
        scope="generated",
        objects=(
            CatalogObject(asset_ref=table, name="Orders", source_id="source"),
            CatalogObject(
                asset_ref=column, name="Amount", source_id="source", table_id=table.asset_id
            ),
            CatalogObject(
                asset_ref=metric,
                name="Revenue",
                table_id=table.asset_id,
                properties=JsonDocument({}),
            ),
        ),
        links=(
            CatalogLink(source=table, target=column, kind="contains"),
            CatalogLink(source=metric, target=column, kind="measures"),
        ),
    )
    with db.session() as session:
        publish_snapshot_in_session(session, snapshot)
        session.commit()
    return table, metric


def test_metric_and_generic_references_enforce_every_underlying_policy(db: Database) -> None:
    """A metric grant cannot replace table/dataset grants; raw data need no metric grant."""
    _dataset(db)
    table, metric = _catalog(db)
    dataset_asset = _asset(db, AssetRef(asset_id="dataset"))
    table_asset = _asset(db, table)
    metric_asset = _asset(db, metric)
    _grant(db, dataset_asset)
    _grant(db, table_asset)
    assert len(require_access(db, (table,), ACCESS, now=NOW)) == 2
    assert (
        len(
            require_access(
                db, (AssetRef(asset_type="resource", asset_id="dataset"),), ACCESS, now=NOW
            )
        )
        == 2
    )
    assert len(require_access(db, (AssetRef(asset_id="dataset"),), ACCESS, now=NOW)) == 2
    with pytest.raises(AuthorizationError):
        require_access(db, (metric,), ACCESS, now=NOW)
    _grant(db, metric_asset)
    assert len(require_access(db, (metric,), ACCESS, now=NOW)) == 3
    assert (
        len(
            require_access(
                db, (AssetRef(asset_type="resource", asset_id=metric.asset_id),), ACCESS, now=NOW
            )
        )
        == 3
    )
    assert len(require_access(db, (AssetRef(asset_id=table.asset_id),), ACCESS, now=NOW)) == 2


def test_public_duplicate_asset_and_withdrawal_cannot_bypass_protected_asset(db: Database) -> None:
    """All resource wrappers apply, independent of publication order and visibility."""
    _dataset(db)
    target = AssetRef(asset_id="dataset")
    protected = _asset(db, target)
    with db.session() as session:
        asset = create_asset_in_session(
            session,
            DataAssetDefinition(
                target=target, name="Public duplicate", owner="Owner", classification="public"
            ),
            _context(),
        )
        set_status_in_session(session, asset.id, "published", _context())
        set_status_in_session(session, protected, "withdrawn", _context())
        session.commit()
    with pytest.raises(AuthorizationError):
        require_access(db, (target,), ACCESS, now=NOW)
    assert list_usage(db, AssetUsageQuery()) == ()
    _grant_before_withdrawal(db, protected)
    assert len(require_access(db, (target, target), ACCESS, now=NOW)) == 2


def _grant_before_withdrawal(db: Database, asset_id: str) -> None:
    with db.session() as session:
        set_status_in_session(session, asset_id, "published", _context())
        session.commit()
    _grant(db, asset_id)
    with db.session() as session:
        set_status_in_session(session, asset_id, "withdrawn", _context())
        session.commit()


def test_derived_outputs_inherit_protected_dataset_grants(db: Database) -> None:
    """Lineage and version-aware source ownership extend through generated outputs."""
    _dataset(db)
    asset_id = _asset(db, AssetRef(asset_id="dataset", version="v1"))
    derived = AssetRef(asset_type="image_transcript", asset_id="derived", version="content")
    with db.session() as session:
        append_event(
            session,
            LineageEvent(
                idempotency_key="derive",
                operator="generated",
                inputs=[AssetRef(asset_type="file", asset_id="file", version="v1")],
                outputs=[derived],
            ),
        )
        session.commit()
    with pytest.raises(AuthorizationError):
        require_access(db, (derived,), ACCESS, now=NOW)
    _grant(db, asset_id)
    assert len(require_access(db, (derived,), ACCESS, now=NOW)) == 1
    with db.session() as session:
        refs = resolve_access_targets(session, (derived,))
    assert AssetRef(asset_id="dataset", version="v1") in refs


def test_original_unversioned_file_inherits_dataset_policy(db: Database) -> None:
    """A pre-migration dataset without version rows still owns its raw manifest files."""
    file = FileItem(id="original", path="fixture.txt", filename="fixture.txt")
    with db.session() as session:
        session.add(DatasetRow(id="original-dataset", name="Generated", files=[file.model_dump()]))
        session.commit()
    asset_id = _asset(db, AssetRef(asset_id="original-dataset"))
    raw = AssetRef(asset_type="file", asset_id="original")
    with pytest.raises(AuthorizationError):
        require_access(db, (raw,), ACCESS, now=NOW)
    _grant(db, asset_id)
    assert len(require_access(db, (raw,), ACCESS, now=NOW)) == 1


def test_valid_grant_does_not_authorize_clock_before_approval(db: Database) -> None:
    """An injected clock cannot backdate use before the grant's creation."""
    _dataset(db)
    target = AssetRef(asset_id="dataset")
    asset_id = _asset(db, target)
    _grant(db, asset_id)
    with pytest.raises(AuthorizationError):
        require_access(db, (target,), ACCESS, now=NOW - timedelta(seconds=1))
    assert require_access(db, (target,), ACCESS, now=NOW, record=False) == ()
    assert list_usage(db, AssetUsageQuery()) == ()


def test_table_card_aggregates_related_metrics_and_latest_observation(db: Database) -> None:
    """Table cards include consuming metrics, measured quality and observed freshness."""
    _dataset(db)
    table, metric = _catalog(db)
    asset_id = _asset(db, table)
    with db.session() as session:
        append_event(
            session,
            LineageEvent(
                idempotency_key="observe",
                operator="generated",
                outputs=[table],
                occurred_at=NOW - timedelta(seconds=30),
            ),
        )
        session.commit()
    card = get_asset_card(db, asset_id, now=NOW)
    assert card.related_metrics == (metric,)
    assert card.quality_score == 100
    assert card.freshness_seconds == 30
    assert card.downstream_count == 2


def _unrelated_table(db: Database) -> tuple[AssetRef, AssetRef]:
    table = AssetRef(asset_type="table", asset_id="source/main/customers")
    metric = AssetRef(asset_type="metric", asset_id="customer_count", version="1")
    with db.session() as session:
        publish_snapshot_in_session(
            session,
            CatalogSnapshot(
                scope="other-table",
                objects=(
                    CatalogObject(asset_ref=table, name="Customers", source_id="source"),
                    CatalogObject(asset_ref=metric, name="Customers", table_id=table.asset_id),
                ),
            ),
        )
        session.commit()
    return table, metric


def test_controlled_import_receipt_keeps_single_table_lineage_and_freshness(db: Database) -> None:
    """A whole-catalog import receipt cannot connect independent tables sharing a source."""
    table, metric = _catalog(db)
    other_table, other_metric = _unrelated_table(db)
    asset_id = _asset(db, table)
    with db.session() as session:
        append_event(
            session,
            LineageEvent(
                idempotency_key="table-observation",
                operator="generated",
                outputs=[table],
                occurred_at=NOW - timedelta(seconds=30),
            ),
        )
        append_event(
            session,
            LineageEvent(
                idempotency_key="controlled-import-receipt",
                operator="import_catalog",
                source_module="actions",
                inputs=[table, metric, other_table, other_metric],
                outputs=[table, metric, other_table, other_metric],
                occurred_at=NOW,
            ),
        )
        session.commit()
    card = get_asset_card(db, asset_id, now=NOW)
    assert card.upstream == ()
    assert card.related_metrics == (metric,)
    assert {ref.asset_id for ref in card.downstream} == {"source/main/orders/amount", "revenue"}
    assert card.downstream_count == 2
    assert card.freshness_seconds == 30


def test_view_reads_enforce_derived_table_policies_and_combine_source_quality(db: Database) -> None:
    """Derived fields inherit base table policies and combine source quality conservatively."""
    _dataset(db)
    table, _metric = _catalog(db)
    source = AssetRef(asset_type="table", asset_id="other/main/base")
    column = AssetRef(asset_type="column", asset_id="other/main/base/value")
    bad = FileItem(id="bad-source", path="fixture.txt", filename="fixture.txt", size=0)
    with db.session() as session:
        session.add(
            DatasetRow(
                id="other-dataset",
                name="Other source",
                files=[bad.model_dump()],
                metadata_values={"source_id": "other"},
            )
        )
        session.flush()
        session.add(
            VersionRow(id="other-v1", dataset_id="other-dataset", manifest=[bad.model_dump()])
        )
        publish_snapshot_in_session(
            session,
            CatalogSnapshot(
                scope="other",
                objects=(
                    CatalogObject(asset_ref=source, name="Base", source_id="other"),
                    CatalogObject(
                        asset_ref=column, name="Value", source_id="other", table_id=source.asset_id
                    ),
                ),
                links=(
                    CatalogLink(source=source, target=column, kind="contains"),
                    CatalogLink(
                        source=column,
                        target=AssetRef(asset_type="column", asset_id="source/main/orders/amount"),
                        kind="derived",
                    ),
                ),
            ),
        )
        session.commit()
    protected = _asset(db, source)
    view_asset = _asset(db, table)
    with pytest.raises(AuthorizationError):
        require_access(db, (table,), ACCESS, now=NOW)
    _grant(db, protected)
    _grant(db, view_asset)
    assert len(require_access(db, (table,), ACCESS, now=NOW)) == 2
    card = get_asset_card(db, view_asset, now=NOW)
    assert card.quality_score is not None
    assert card.quality_score < 100
    assert card.quality_trend[-1].score == card.quality_score


def _two_metrics(db: Database) -> tuple[AssetRef, AssetRef, str]:
    _dataset(db)
    _table, first = _catalog(db)
    other = AssetRef(asset_type="metric", asset_id="unrelated", version="1")
    with db.session() as session:
        publish_snapshot_in_session(
            session,
            CatalogSnapshot(
                scope="unrelated",
                objects=(
                    CatalogObject(asset_ref=other, name="Unrelated", properties=JsonDocument({})),
                ),
            ),
        )
        session.commit()
    first_asset = _asset(db, first)
    _asset(db, other)
    _grant(db, first_asset)
    return first, other, first_asset


def test_metadata_batch_receipt_does_not_add_unrelated_metric_policy(db: Database) -> None:
    """Snapshot management receipts do not create dependencies between unrelated objects."""
    first, other, asset_id = _two_metrics(db)
    with db.session() as session:
        append_event(
            session,
            LineageEvent(
                idempotency_key="batch-receipt",
                operator="update_metric",
                inputs=[first, other],
                outputs=[first, other],
            ),
        )
        session.commit()
    assert [use.asset_id for use in require_access(db, (first,), ACCESS, now=NOW)] == [asset_id]
    with pytest.raises(AuthorizationError):
        require_access(db, (other,), ACCESS, now=NOW)


def test_one_assertion_in_batch_uses_its_own_endpoints_and_source_anchors(db: Database) -> None:
    """A link to one authorized metric never demands another link's unrelated metric grant."""
    first, other, asset_id = _two_metrics(db)
    source = AssetRef(asset_type="file", asset_id="file", version="v1")
    event = LineageEvent(
        idempotency_key="batch-links",
        operator="evidence.kg_link",
        inputs=[first, other, source],
        outputs=[AssetRef(asset_type="knowledge_bundle", asset_id="batch", version="1")],
    )
    fact = Assertion(
        id="link",
        subject=AssetRef(asset_type="kg_entity", asset_id="entity", version="v1"),
        predicate="link.maps_to",
        object=first,
        anchors=(EvidenceAnchor(asset_ref=source, content_revision="a" * 64),),
        extractor=ExtractorRef(id="generated", version="1"),
        producer_event_id=event.event_id,
        run_id="batch",
    )
    with db.session() as session:
        append_event(session, event)
        session.add(
            AssertionRow(
                id=fact.id,
                subject_id=fact.subject.asset_id,
                predicate=fact.predicate,
                producer_event_id=event.event_id,
                payload=fact.model_dump(mode="json"),
            )
        )
        session.commit()
    ref = AssetRef(asset_type="assertion", asset_id=fact.id, version=fact.id)
    assert [use.asset_id for use in require_access(db, (ref,), ACCESS, now=NOW)] == [asset_id]
