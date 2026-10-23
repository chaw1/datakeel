# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Content cache projection and auditable extractor or input invalidation."""

from itertools import batched

from sqlalchemy import insert, select
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
    priors = _cache_rows(session, bundle)
    old_entries = {
        slot: EvidenceCacheEntry.model_validate(row.payload) for slot, row in priors.items()
    }
    identifiers = {identifier for old in old_entries.values() for identifier in old.assertion_ids}
    assertions = {
        row.id: row
        for batch in batched(identifiers, 500)
        for row in session.scalars(
            select(AssertionRow).where(AssertionRow.id.in_(batch), AssertionRow.active.is_(True))
        )
    }
    for entry in bundle.cache_entries:
        prior = priors.get(entry.slot)
        if prior is None:
            continue
        old = old_entries[entry.slot]
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
            row = assertions.get(identifier)
            if row is not None and identifier not in seen:
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
    rows = _cache_rows(session, bundle)
    entries = {entry.slot: entry for entry in bundle.cache_entries}
    pending: list[dict[str, object]] = []
    for slot, entry in entries.items():
        row = rows.get(slot)
        key = entry.key.digest()
        payload = entry.model_dump(mode="json")
        if row is None:
            pending.append(
                {"slot": slot, "cache_key": key, "producer_event_id": event_id, "payload": payload}
            )
        else:
            row.cache_key = key
            row.producer_event_id = event_id
            row.payload = payload
    if pending:
        session.execute(insert(EvidenceCacheRow), pending)


def cache_predecessors(session: Session, bundle: KnowledgeBundle) -> tuple[str, ...]:
    """Read the prior producing event identities in bounded cache-slot batches."""
    return tuple(sorted({row.producer_event_id for row in _cache_rows(session, bundle).values()}))


def _cache_rows(session: Session, bundle: KnowledgeBundle) -> dict[str, EvidenceCacheRow]:
    slots = {entry.slot for entry in bundle.cache_entries}
    return {
        row.slot: row
        for batch in batched(slots, 500)
        for row in session.scalars(select(EvidenceCacheRow).where(EvidenceCacheRow.slot.in_(batch)))
    }
