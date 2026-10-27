# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Publish incremental integration scopes with retained soft deletion evidence."""

from sqlalchemy.orm import Session

from datakeel.core.catalog_canonical import object_content
from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot
from datakeel.core.catalog_projection import snapshot_events
from datakeel.core.metadata_imports import MetadataImportBatch, MetadataImportReport
from datakeel.core.models import JsonDocument
from datakeel.storage.catalog_store import lock_catalog, publish_snapshot_in_session
from datakeel.storage.database import Database
from datakeel.storage.events import all_events


def _deleted(item: CatalogObject) -> bool:
    return item.properties.root.get("source_deleted") is True


def _tombstone(item: CatalogObject) -> CatalogObject:
    properties = {**item.properties.root, "source_deleted": True}
    integration = properties.get("integration")
    if isinstance(integration, dict):
        properties["integration"] = {**integration, "source_deleted": True}
    return item.model_copy(update={"properties": JsonDocument(properties)})


def _prior(session: Session, scope: str) -> CatalogSnapshot:
    snapshots = [value for _, value in snapshot_events(all_events(session)) if value.scope == scope]
    return snapshots[-1] if snapshots else CatalogSnapshot(scope=scope)


def _keep_confirmation(item: CatalogObject, prior: CatalogObject | None) -> CatalogObject:
    if (
        prior is not None
        and item.asset_ref.asset_type == "metric_draft"
        and prior.properties.root.get("status") == "confirmed"
        and item.properties.root.get("raw") == prior.properties.root.get("raw")
        and item.properties.root.get("source_fingerprint")
        == prior.properties.root.get("source_fingerprint")
    ):
        return item.model_copy(
            update={
                "properties": JsonDocument(
                    {
                        **item.properties.root,
                        "status": "confirmed",
                        "definition": prior.properties.root.get("definition"),
                    }
                )
            }
        )
    return item


def publish_metadata_in_session(
    session: Session, batch: MetadataImportBatch, actor: str = "local-user"
) -> MetadataImportReport:
    """Compare stable identities, retain deletions and atomically append one scope snapshot."""
    lock_catalog(session)
    incoming = batch.snapshot
    prior = _prior(session, incoming.scope)
    old = {item.asset_ref.asset_id: item for item in prior.objects}
    incoming = incoming.model_copy(
        update={
            "objects": tuple(
                _keep_confirmation(item, old.get(item.asset_ref.asset_id))
                for item in incoming.objects
            )
        }
    )
    identities = {item.asset_ref.asset_id for item in incoming.objects}
    removed = tuple(item for key, item in old.items() if key not in identities)
    retained = incoming.model_copy(
        update={"objects": incoming.objects + tuple(_tombstone(item) for item in removed)}
    )
    new = sum(item.asset_ref.asset_id not in old for item in incoming.objects)
    unchanged = sum(
        item.asset_ref.asset_id in old
        and object_content(item) == object_content(old[item.asset_ref.asset_id])
        for item in incoming.objects
    )
    result = publish_snapshot_in_session(session, retained, actor=actor)
    return MetadataImportReport.model_validate(
        {
            **result.model_dump(exclude={"failed_sql_count"}),
            "object_count": len(incoming.objects),
            "new": new,
            "changed": len(incoming.objects) - new - unchanged,
            "unchanged": unchanged,
            "deleted": sum(not _deleted(item) for item in removed),
            "drafts": sum(item.asset_ref.asset_type == "metric_draft" for item in incoming.objects),
            "parse_failures": batch.parse_failures,
        }
    )


def publish_metadata(
    db: Database, batch: MetadataImportBatch, actor: str = "local-user"
) -> MetadataImportReport:
    """Serialize metadata imports and commit facts and merged projections together."""
    with db.session() as session:
        db.lock_writes(session)
        result = publish_metadata_in_session(session, batch, actor)
        session.commit()
        return result
