# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Transactional, idempotent metadata versions backed exclusively by lineage events."""

from sqlalchemy.orm import Session

from datakeel.core.catalog_canonical import canonical_content, document_hash, object_content
from datakeel.core.catalog_models import (
    CatalogObject,
    CatalogOperator,
    CatalogSnapshot,
    ImportReport,
)
from datakeel.core.catalog_projection import snapshot_events
from datakeel.core.errors import ValidationError
from datakeel.core.models import LineageEvent, new_id
from datakeel.storage.catalog_locks import lock_catalog
from datakeel.storage.catalog_projection import project_snapshot
from datakeel.storage.catalog_reads import read_snapshot
from datakeel.storage.database import Database
from datakeel.storage.events import all_events, append_event


def _versioned(snapshot: CatalogSnapshot, prior: CatalogSnapshot, event_id: str) -> CatalogSnapshot:
    old = {item.asset_ref.asset_id: item for item in prior.objects}
    result: list[CatalogObject] = []
    for item in snapshot.objects:
        previous = old.get(item.asset_ref.asset_id)
        if previous is not None and object_content(previous) == object_content(item):
            result.append(previous)
        else:
            result.append(
                item.model_copy(
                    update={
                        "revision": previous.revision + 1 if previous else 1,
                        "producer_event_id": event_id,
                    }
                )
            )
    return snapshot.model_copy(
        update={
            "objects": tuple(result),
            "links": tuple(
                link.model_copy(update={"producer_event_id": event_id}) for link in snapshot.links
            ),
        }
    )


def _report(current: CatalogSnapshot, prior: CatalogSnapshot, version: int) -> ImportReport:
    old = {item.asset_ref.asset_id: item for item in prior.objects}
    new = sum(item.asset_ref.asset_id not in old for item in current.objects)
    unchanged = sum(
        item.asset_ref.asset_id in old
        and object_content(item) == object_content(old[item.asset_ref.asset_id])
        for item in current.objects
    )
    return ImportReport(
        object_count=len(current.objects),
        new=new,
        unchanged=unchanged,
        changed=len(current.objects) - new - unchanged,
        link_count=len(current.links),
        snapshot_version=version,
    )


def publish_snapshot_in_session(
    session: Session,
    snapshot: CatalogSnapshot,
    operator: CatalogOperator = "CATALOG_IMPORT",
    actor: str = "local-user",
) -> ImportReport:
    """Append one complete scope version, leaving identical imports event-free."""
    lock_catalog(session)
    identities = [item.asset_ref.asset_id for item in snapshot.objects]
    if len(set(identities)) != len(identities):
        msg = "Catalog snapshots require unique object identities"
        raise ValidationError(msg)
    history = [
        value for _, value in snapshot_events(all_events(session)) if value.scope == snapshot.scope
    ]
    prior = history[-1] if history else CatalogSnapshot(scope=snapshot.scope)
    report = _report(snapshot, prior, len(history))
    if canonical_content(snapshot) == canonical_content(prior):
        return report
    event_id = new_id()
    version = len(history) + 1
    snapshot = _versioned(snapshot, prior, event_id)
    digest = document_hash(canonical_content(snapshot))
    event = LineageEvent(
        event_id=event_id,
        idempotency_key=f"catalog:{snapshot.scope}:{version}:{digest}",
        operator=operator,
        source_module="catalog",
        on_behalf_of=actor,
        outputs=[item.asset_ref for item in snapshot.objects],
        params={"catalog_snapshot": snapshot.model_dump(mode="json"), "snapshot_version": version},
    )
    append_event(session, event)
    project_snapshot(session, snapshot)
    session.flush()
    return report.model_copy(update={"event_id": event_id, "snapshot_version": version})


def publish_snapshot(
    db: Database,
    snapshot: CatalogSnapshot,
    operator: CatalogOperator = "CATALOG_IMPORT",
    actor: str = "local-user",
) -> ImportReport:
    """Serialize metadata writers and atomically publish their snapshot event."""
    with db.session() as session:
        db.lock_writes(session)
        result = publish_snapshot_in_session(session, snapshot, operator, actor)
        session.commit()
        return result


__all__ = ["lock_catalog", "publish_snapshot", "publish_snapshot_in_session", "read_snapshot"]
