# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Publish reviewable catalog associations inside graph and catalog transactions."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.evidence_cache import KnowledgeBundle
from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_models import Assertion, AssertionDecision
from datakeel.core.link_models import LinkRunResult
from datakeel.core.models import AssetRef, LineageEvent, new_id
from datakeel.storage.catalog_locks import lock_catalog
from datakeel.storage.catalog_reads import read_snapshot
from datakeel.storage.database import Database
from datakeel.storage.evidence_decisions import append_decision, assertion_view
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.evidence_store import record_extraction_in_session
from datakeel.storage.link_context import read_link_graphs
from datakeel.storage.link_drafts import link_drafts, link_identity
from datakeel.storage.link_reviews import inherit_link_reviews, latest_link_reviews


def _event(drafts: tuple[ObservationDraft, ...]) -> LineageEvent:
    identifier = new_id()
    inputs = {
        ref.model_dump_json(): ref
        for draft in drafts
        for ref in (
            draft.subject,
            *([draft.object] if isinstance(draft.object, AssetRef) else []),
            *(anchor.asset_ref for anchor in draft.anchors),
        )
    }
    return LineageEvent(
        event_id=identifier,
        idempotency_key=f"kg-link:{identifier}",
        event_type="COMPLETE",
        operator="evidence.kg_link",
        source_module="storage",
        inputs=[inputs[key] for key in sorted(inputs)],
        outputs=[AssetRef(asset_type="knowledge_bundle", asset_id=identifier, version="1.0")],
        params={"run_id": identifier},
    )


def _change_activity(
    session: Session, event: LineageEvent, row: AssertionRow, *, active: bool
) -> None:
    assertion = assertion_view(row)
    append_decision(
        session,
        AssertionDecision(
            assertion_id=assertion.id,
            action="reactivate" if active else "invalidate",
            previous_status=assertion.status,
            status=assertion.status,
            actor=event.operator,
            reason="current_entity_catalog_link" if active else "entity_or_catalog_link_replaced",
            producer_event_id=event.event_id,
            occurred_at=event.occurred_at,
        ),
        f"link-activity:{event.event_id}:{assertion.id}",
    )


def relink_in_session(session: Session) -> LinkRunResult:
    """Refresh current links atomically, preserving direct reviews across all versions."""
    lock_catalog(session)
    graphs = read_link_graphs(session)
    drafts = link_drafts(graphs, read_snapshot(session), latest_link_reviews(session))
    desired = {link_identity(draft): draft for draft in drafts}
    existing = {
        row.id: row
        for row in session.scalars(
            select(AssertionRow).where(AssertionRow.predicate == "link.maps_to")
        )
    }
    active = {key for key, row in existing.items() if row.active}
    created = desired.keys() - existing.keys()
    invalidated = active - desired.keys()
    result = LinkRunResult(
        entities=sum(len(graph.entities) for graph in graphs),
        links=len(desired),
        created=len(created),
        invalidated=len(invalidated),
    )
    if desired.keys() == active:
        return result
    event = _event(drafts)
    assertions = tuple(
        Assertion(
            **desired[key].model_dump(),
            id=key,
            producer_event_id=event.event_id,
            run_id=str(event.params["run_id"]),
            created_at=event.occurred_at,
        )
        for key in sorted(created)
    )
    record_extraction_in_session(
        session, event, KnowledgeBundle(run_id=str(event.params["run_id"]), assertions=assertions)
    )
    for key in sorted(invalidated):
        _change_activity(session, event, existing[key], active=False)
    for key in sorted(desired.keys() & existing.keys() - active):
        _change_activity(session, event, existing[key], active=True)
    inherit_link_reviews(session, event, set(desired))
    return result


def relink(db: Database) -> LinkRunResult:
    """Recompute all current graph links with no model calls or external access."""
    with db.session() as session:
        db.lock_writes(session)
        result = relink_in_session(session)
        session.commit()
        return result
