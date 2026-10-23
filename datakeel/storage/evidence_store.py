# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validated extraction publication and typed evidence projection reads."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.evidence_cache import KnowledgeBundle
from datakeel.core.evidence_models import Assertion
from datakeel.core.models import AssetRef, LineageEvent
from datakeel.storage.database import Database, EventRow
from datakeel.storage.events import append_event
from datakeel.storage.evidence_artifacts import load_bundle, publish_bundle
from datakeel.storage.evidence_cache import invalidations_for, project_cache
from datakeel.storage.evidence_decisions import append_decision, assertion_view
from datakeel.storage.evidence_rows import AssertionRow, EvidenceCacheRow


def _identity(ref: AssetRef) -> tuple[str, str, str, str | None]:
    return ref.namespace, ref.asset_type, ref.asset_id, ref.version


def validated_bundle(event: LineageEvent, bundle: KnowledgeBundle | None = None) -> KnowledgeBundle:
    """Reject observations without complete extraction provenance or source inputs."""
    if (
        event.event_type != "COMPLETE"
        or event.run_state not in {"COMPLETE", "COMPLETED"}
        or not event.operator.startswith("evidence.")
        or not any(ref.asset_type == "knowledge_bundle" for ref in event.outputs)
    ):
        msg = "Assertions require a COMPLETE evidence extraction event and knowledge bundle output"
        raise ValidationError(msg)
    bundle = bundle or load_bundle(event)
    if any(item.extractor.id != event.operator for item in bundle.assertions) or any(
        entry.key.extractor.id != event.operator for entry in bundle.cache_entries
    ):
        msg = "Assertion and cache extractors must match their producing event operator"
        raise ValidationError(msg)
    if bundle.run_id != event.params.get("run_id"):
        msg = "Knowledge bundle run must match event params.run_id"
        raise ValidationError(msg)
    inputs = {_identity(ref) for ref in event.inputs}
    if any(_identity(entry.subject) not in inputs for entry in bundle.cache_entries):
        msg = "Cache subjects must belong to the extraction inputs"
        raise ValidationError(msg)
    for assertion in bundle.assertions:
        references = [assertion.subject, *(anchor.asset_ref for anchor in assertion.anchors)]
        if isinstance(assertion.object, AssetRef):
            references.append(assertion.object)
        if (
            assertion.producer_event_id != event.event_id
            or assertion.run_id != bundle.run_id
            or assertion.status != "candidate"
            or assertion.decided_by is not None
            or assertion.decided_at is not None
            or any(_identity(ref) not in inputs for ref in references)
        ):
            msg = "Assertion content must bind this extraction event and its versioned inputs"
            raise ValidationError(msg)
    if any(
        decision.action != "invalidate" or decision.producer_event_id != event.event_id
        for decision in bundle.invalidations
    ):
        msg = "Bundle invalidations must belong to their producing extraction event"
        raise ValidationError(msg)
    return bundle


def project_bundle(session: Session, event: LineageEvent, bundle: KnowledgeBundle) -> None:
    """Project validated event content without overwriting immutable observations."""
    for assertion in bundle.assertions:
        row = session.get(AssertionRow, assertion.id)
        payload = assertion.model_dump(mode="json")
        if row is not None:
            if row.payload != payload:
                msg = "An assertion identity already binds different immutable content"
                raise ConflictError(msg)
            continue
        session.add(
            AssertionRow(
                id=assertion.id,
                subject_id=assertion.subject.asset_id,
                predicate=assertion.predicate,
                producer_event_id=event.event_id,
                payload=payload,
                status="candidate",
                active=True,
            )
        )
    session.flush()
    for decision in bundle.invalidations:
        append_decision(session, decision, f"invalidation:{decision.id}")
    project_cache(session, bundle, event.event_id)


def record_extraction(
    db: Database, event: LineageEvent, bundle: KnowledgeBundle | None = None
) -> LineageEvent:
    """Atomically append a COMPLETE bundle, its invalidation audit, and projection."""
    with db.session() as session:
        db.lock_writes(session)
        result = record_extraction_in_session(session, event, bundle)
        session.commit()
        return result


def record_extraction_in_session(
    session: Session, event: LineageEvent, bundle: KnowledgeBundle | None = None
) -> LineageEvent:
    """Publish extraction inside the caller's fenced worker completion transaction."""
    if bundle is None:
        value = event.params.get("knowledge_bundle")
        if isinstance(value, dict) and "object_key" in value:
            return _replay_artifact(session, event)
        bundle = KnowledgeBundle.model_validate(value)
    bundle = validated_bundle(event, bundle)
    if bundle.invalidations or bundle.prior_cache_event_ids:
        msg = "Invalidations and cache predecessors are derived by storage"
        raise ValidationError(msg)
    prior = session.scalar(
        select(EventRow).where(EventRow.idempotency_key == event.idempotency_key)
    )
    if prior is not None:
        result = LineageEvent.model_validate(prior.payload)
        previous = validated_bundle(result).model_copy(
            update={"invalidations": (), "prior_cache_event_ids": ()}
        )
        if previous != bundle:
            msg = "Extraction idempotency key already binds different run content"
            raise ConflictError(msg)
        return result
    predecessors = {
        prior.producer_event_id
        for entry in bundle.cache_entries
        if (prior := session.get(EvidenceCacheRow, entry.slot)) is not None
    }
    bundle = bundle.model_copy(
        update={
            "invalidations": invalidations_for(session, bundle, event),
            "prior_cache_event_ids": tuple(sorted(predecessors)),
        }
    )
    result = publish_bundle(event, bundle)
    append_event(session, result)
    project_bundle(session, result, bundle)
    return result


def _replay_artifact(session: Session, event: LineageEvent) -> LineageEvent:
    validated_bundle(event)
    prior = session.scalar(
        select(EventRow).where(EventRow.idempotency_key == event.idempotency_key)
    )
    if prior is None:
        msg = "Artifact replay requires a previously stored COMPLETE event"
        raise ValidationError(msg)
    recorded = LineageEvent.model_validate(prior.payload)
    if recorded != event:
        msg = "Extraction artifact replay must match its immutable stored event"
        raise ConflictError(msg)
    return recorded


def read_assertions(
    session: Session, asset_id: str | None = None, *, include_invalidated: bool = False
) -> list[Assertion]:
    """Read immutable content with reviewed status inside an existing transaction."""
    statement = select(AssertionRow).order_by(AssertionRow.id)
    if asset_id is not None:
        statement = statement.where(AssertionRow.subject_id == asset_id)
    if not include_invalidated:
        statement = statement.where(AssertionRow.active.is_(True))
    return [assertion_view(row) for row in session.scalars(statement)]


def list_assertions(
    db: Database, asset_id: str | None = None, *, include_invalidated: bool = False
) -> list[Assertion]:
    """Return typed observations without leaking persistence rows across boundaries."""
    with db.session() as session:
        return read_assertions(session, asset_id, include_invalidated=include_invalidated)
