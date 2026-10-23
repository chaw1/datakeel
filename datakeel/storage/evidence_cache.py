# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Content cache projection and auditable extractor or input invalidation."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.evidence_cache import EvidenceCacheEntry, EvidenceCacheKey, KnowledgeBundle
from datakeel.core.evidence_models import AssertionDecision
from datakeel.core.models import AssetRef, LineageEvent
from datakeel.storage.database import Database
from datakeel.storage.evidence_decisions import assertion_view
from datakeel.storage.evidence_rows import AssertionRow, EvidenceCacheRow


def cached_entry(
    db: Database, subject: AssetRef, key: EvidenceCacheKey
) -> EvidenceCacheEntry | None:
    """Return a cache hit only when every input, selector, and version matches."""
    slot = EvidenceCacheEntry(subject=subject, key=key, assertion_ids=()).slot
    with db.session() as session:
        row = session.get(EvidenceCacheRow, slot)
        if row is None or row.cache_key != key.digest():
            return None
        entry = EvidenceCacheEntry.model_validate(row.payload)
        if any(
            (assertion := session.get(AssertionRow, identifier)) is None or not assertion.active
            for identifier in entry.assertion_ids
        ):
            return None
        return entry


def cached_entries(
    db: Database, requests: tuple[EvidenceCacheEntry, ...]
) -> tuple[EvidenceCacheEntry, ...]:
    """Read an entire node's candidate cache slots in one short-lived transaction."""
    keys = {request.slot: request.key.digest() for request in requests}
    with db.session() as session:
        rows = list(
            session.scalars(select(EvidenceCacheRow).where(EvidenceCacheRow.slot.in_(keys)))
        )
        candidates = [
            EvidenceCacheEntry.model_validate(row.payload)
            for row in rows
            if row.cache_key == keys[row.slot]
        ]
        identifiers = {identifier for entry in candidates for identifier in entry.assertion_ids}
        active = set(
            session.scalars(
                select(AssertionRow.id).where(
                    AssertionRow.id.in_(identifiers), AssertionRow.active.is_(True)
                )
            )
        )
        return tuple(
            entry for entry in candidates if all(value in active for value in entry.assertion_ids)
        )


def invalidations_for(
    session: Session, bundle: KnowledgeBundle, event: LineageEvent
) -> tuple[AssertionDecision, ...]:
    """Materialize obsolete assertion decisions before their event is appended."""
    decisions: list[AssertionDecision] = []
    seen: set[str] = set()
    for entry in bundle.cache_entries:
        prior = session.get(EvidenceCacheRow, entry.slot)
        if prior is None:
            continue
        old = EvidenceCacheEntry.model_validate(prior.payload)
        if prior.cache_key == entry.key.digest() and old.assertion_ids == entry.assertion_ids:
            continue
        reason = (
            "extractor_version_changed"
            if old.key.extractor != entry.key.extractor
            else "input_content_or_selector_changed"
            if old.key != entry.key
            else "superseded_extraction"
        )
        for identifier in old.assertion_ids:
            row = session.get(AssertionRow, identifier)
            if row is not None and row.active and identifier not in seen:
                seen.add(identifier)
                assertion = assertion_view(row)
                decisions.append(
                    AssertionDecision(
                        assertion_id=identifier,
                        action="invalidate",
                        previous_status=assertion.status,
                        status=assertion.status,
                        actor=entry.key.extractor.id,
                        reason=reason,
                        producer_event_id=event.event_id,
                        occurred_at=event.occurred_at,
                    )
                )
    return tuple(decisions)


def project_cache(session: Session, bundle: KnowledgeBundle, event_id: str) -> None:
    """Replace disposable cache slots with products declared in the current event."""
    for entry in bundle.cache_entries:
        row = session.get(EvidenceCacheRow, entry.slot)
        if row is None:
            row = EvidenceCacheRow(slot=entry.slot)
            session.add(row)
        row.cache_key = entry.key.digest()
        row.producer_event_id = event_id
        row.payload = entry.model_dump(mode="json")
