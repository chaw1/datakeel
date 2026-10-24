# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Atomic, reversible decision overlays without mutation of extracted content."""

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from datakeel.core.errors import ConflictError, NotFoundError
from datakeel.core.evidence_models import Assertion, AssertionDecision, AssertionDecisionRequest
from datakeel.core.kg_contracts import KGSchema
from datakeel.core.kg_registry import register_kg_schema
from datakeel.core.predicate_registry import registered_predicates
from datakeel.storage.database import Database, EventRow
from datakeel.storage.evidence_rows import AssertionDecisionRow, AssertionRow


def assertion_view(row: AssertionRow) -> Assertion:
    """Overlay reviewed status on the original immutable assertion payload."""
    _restore_vocabulary(row)
    return Assertion.model_validate(
        {
            **row.payload,
            "status": row.status,
            "decided_by": row.decided_by,
            "decided_at": row.decided_at,
        }
    )


def _restore_vocabulary(row: AssertionRow) -> None:
    if not row.predicate.startswith("kg.") or any(
        item.id == row.predicate for item in registered_predicates()
    ):
        return
    session = object_session(row)
    event = session.get(EventRow, row.producer_event_id) if session is not None else None
    if event is not None and "kg_schema" in event.payload.get("params", {}):
        register_kg_schema(KGSchema.model_validate(event.payload["params"]["kg_schema"]))


def append_decision(session: Session, decision: AssertionDecision, key: str) -> None:
    """Append an idempotent audit entry and apply its projection state."""
    prior = session.scalar(
        select(AssertionDecisionRow).where(AssertionDecisionRow.idempotency_key == key)
    )
    if prior is not None:
        return
    session.add(
        AssertionDecisionRow(
            id=decision.id,
            idempotency_key=key,
            assertion_id=decision.assertion_id,
            payload=decision.model_dump(mode="json"),
        )
    )
    apply_decision(session, decision)


def apply_decision(session: Session, decision: AssertionDecision) -> None:
    """Replay a single audit entry onto a disposable observation projection."""
    row = session.get(AssertionRow, decision.assertion_id)
    if row is None:
        msg = "Assertion not found"
        raise NotFoundError(msg)
    if decision.action == "invalidate":
        row.active = False
    elif decision.action == "reactivate":
        row.active = True
    else:
        row.status = decision.status
        row.decided_by = decision.actor
        row.decided_at = decision.occurred_at.isoformat()


def decide_in_session(session: Session, request: AssertionDecisionRequest) -> list[Assertion]:
    """Apply a complete decision batch inside a caller-owned action transaction."""
    result: list[Assertion] = []
    for identifier in sorted(set(request.assertion_ids)):
        row = session.scalar(
            select(AssertionRow).where(AssertionRow.id == identifier).with_for_update()
        )
        if row is None:
            msg = "Assertion not found"
            raise NotFoundError(msg)
        if not row.active:
            msg = "Invalidated assertions are read-only audit history"
            raise ConflictError(msg)
        key = f"{request.idempotency_key}:{identifier}"
        prior = session.scalar(
            select(AssertionDecisionRow).where(AssertionDecisionRow.idempotency_key == key)
        )
        if prior is not None:
            _validate_retry(AssertionDecision.model_validate(prior.payload), request)
        else:
            current = assertion_view(row)
            append_decision(
                session,
                AssertionDecision(
                    assertion_id=identifier,
                    action=(
                        "accept"
                        if request.status == "accepted"
                        else "reject"
                        if request.status == "rejected"
                        else "restore"
                    ),
                    previous_status=current.status,
                    status=request.status,
                    actor=request.actor,
                    reason=request.reason,
                ),
                key,
            )
        result.append(assertion_view(row))
    return result


def _validate_retry(prior: AssertionDecision, request: AssertionDecisionRequest) -> None:
    if (prior.status, prior.actor, prior.reason) != (request.status, request.actor, request.reason):
        msg = "Decision idempotency key already binds different parameters"
        raise ConflictError(msg)


def decide_assertions(db: Database, request: AssertionDecisionRequest) -> list[Assertion]:
    """Commit a reversible decision batch together with all of its audit records."""
    with db.session() as session:
        db.lock_writes(session)
        result = decide_in_session(session, request)
        session.commit()
        return result


def list_decisions(db: Database, assertion_id: str | None = None) -> list[AssertionDecision]:
    """Read decision audit history in append order."""
    with db.session() as session:
        statement = select(AssertionDecisionRow).order_by(AssertionDecisionRow.sequence)
        if assertion_id:
            statement = statement.where(AssertionDecisionRow.assertion_id == assertion_id)
        return [AssertionDecision.model_validate(row.payload) for row in session.scalars(statement)]
