# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validated extraction publication and typed evidence projection reads."""

from itertools import batched

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.evidence_cache import KnowledgeBundle
from datakeel.core.evidence_models import Assertion
from datakeel.core.kg_contracts import KGSchema
from datakeel.core.kg_registry import register_kg_schema
from datakeel.core.models import AssetRef, LineageEvent
from datakeel.storage.database import Database, EventRow
from datakeel.storage.events import append_event
from datakeel.storage.evidence_artifacts import load_bundle, publish_bundle
from datakeel.storage.evidence_cache import cache_predecessors, invalidations_for, project_cache
from datakeel.storage.evidence_decisions import append_decision, assertion_view
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.kg_provenance import kg_predecessors


def _identity(ref: AssetRef) -> tuple[str, str, str, str | None]:
    return ref.namespace, ref.asset_type, ref.asset_id, ref.version


def _references_bound(event: LineageEvent, assertion: Assertion) -> bool:
    inputs = {_identity(ref) for ref in event.inputs}
    if any(_identity(anchor.asset_ref) not in inputs for anchor in assertion.anchors):
        return False
    allowed = inputs
    if event.operator == "evidence.kg" and assertion.predicate.startswith("kg."):
        allowed = inputs | {
            _identity(ref) for ref in event.outputs if ref.asset_type == "kg_entity"
        }
    endpoints = [assertion.subject]
    if isinstance(assertion.object, AssetRef):
        endpoints.append(assertion.object)
    return all(_identity(ref) in allowed for ref in endpoints)


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
    if "kg_schema" in event.params:
        register_kg_schema(KGSchema.model_validate(event.params["kg_schema"]))
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
        if (
            assertion.producer_event_id != event.event_id
            or assertion.run_id != bundle.run_id
            or assertion.status != "candidate"
            or assertion.decided_by is not None
            or assertion.decided_at is not None
            or not _references_bound(event, assertion)
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
    payloads = {
        identifier: payload
        for identifiers in batched((assertion.id for assertion in bundle.assertions), 500)
        for identifier, payload in session.execute(
            select(AssertionRow.id, AssertionRow.payload).where(AssertionRow.id.in_(identifiers))
        )
    }
    pending: list[dict[str, object]] = []
    for assertion in bundle.assertions:
        payload = assertion.model_dump(mode="json")
        if assertion.id in payloads:
            if payloads[assertion.id] != payload:
                msg = "An assertion identity already binds different immutable content"
                raise ConflictError(msg)
            continue
        payloads[assertion.id] = payload
        pending.append(
            {
                "id": assertion.id,
                "subject_id": assertion.subject.asset_id,
                "predicate": assertion.predicate,
                "producer_event_id": event.event_id,
                "payload": payload,
                "status": "candidate",
                "active": True,
                "verification": assertion.verification,
                "verification_detail": (
                    assertion.verification_detail.model_dump(mode="json")
                    if assertion.verification_detail is not None
                    else None
                ),
            }
        )
    if pending:
        session.execute(insert(AssertionRow), pending)
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
    predecessors = tuple(
        sorted(set(cache_predecessors(session, bundle)) | set(kg_predecessors(session, event)))
    )
    bundle = bundle.model_copy(
        update={
            "invalidations": invalidations_for(session, bundle, event),
            "prior_cache_event_ids": predecessors,
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
