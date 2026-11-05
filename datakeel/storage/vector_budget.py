# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Durable fake request/cost occupancy with conservative unknown-outcome recovery."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.models import utcnow
from datakeel.core.vector_models import FrozenPayload, VectorAttempt, VectorError, VectorPermit
from datakeel.storage.budget_accounts import lock_budget
from datakeel.storage.database import Database
from datakeel.storage.vector_authorization import authorize_vector
from datakeel.storage.vector_rows import VectorAccountRow, VectorAttemptRow


def _view(row: VectorAttemptRow) -> VectorAttempt:
    return VectorAttempt.model_validate(
        {
            "id": row.id,
            "state": row.state,
            "token_bound": row.token_bound,
            "reserved_nanos": row.reserved_nanos,
            "usage": row.payload.get("usage"),
            "response_id": row.payload.get("response_id"),
            "reason": row.payload.get("reason"),
        }
    )


def _transition(row: VectorAttemptRow, state: str, **details: object) -> None:
    row.state = state
    row.payload = {
        **row.payload,
        **details,
        "history": [
            *row.payload.get("history", []),
            {"state": state, "at": utcnow().isoformat(), **details},
        ],
    }


def reserve_vector(
    db: Database, permit: VectorPermit, node_id: str, payload: FrozenPayload
) -> VectorAttempt:
    """Atomically occupy a request and worst cost before dispatch, exactly once."""
    with db.session() as session:
        lock_budget(db, session)
        prepared = authorize_vector(session, permit)
        node = next((node for node in prepared.nodes if node.node_id == node_id), None)
        if (
            node is None
            or payload not in node.inputs
            or payload.failure
            or payload.asset_id not in node.actual_asset_ids
        ):
            msg = "vector_payload_not_approved"
            raise VectorError(msg)
        policy = node.params.policy
        account = _account(session, permit.plan_id)
        existing = session.scalar(
            select(VectorAttemptRow).where(
                VectorAttemptRow.task_id == permit.task_id,
                VectorAttemptRow.node_id == node_id,
                VectorAttemptRow.asset_id == payload.asset_id,
            )
        )
        if existing is not None:
            msg = "vector_attempt_cannot_retry"
            raise VectorError(msg)
        cost = payload.token_bound * policy.nanos_per_token
        if (
            account.requests + 1 > policy.max_requests
            or account.cost_nanos + cost > policy.max_cost_nanos
        ):
            msg = "vector_budget_exceeded"
            raise VectorError(msg)
        account.requests += 1
        account.cost_nanos += cost
        row = VectorAttemptRow(
            plan_id=permit.plan_id,
            task_id=permit.task_id,
            node_id=node_id,
            asset_id=payload.asset_id,
            token_bound=payload.token_bound,
            reserved_nanos=cost,
            payload={
                "permit": permit.model_dump(mode="json"),
                "policy": policy.model_dump(mode="json"),
                "content_hash": payload.content_revision,
                "body_hash": payload.body_hash,
                "payload_hash": payload.payload_hash,
                "mode": "fake",
                "history": [],
            },
        )
        session.add(row)
        _transition(row, "RESERVED")
        session.commit()
        return _view(row)


def dispatch_vector(
    db: Database, permit: VectorPermit, attempt_id: str, payload: FrozenPayload
) -> None:
    """Persist SENDING before the fake boundary, making every subsequent outcome uncertain."""
    with db.session() as session:
        lock_budget(db, session)
        prepared = authorize_vector(session, permit)
        row = session.get(VectorAttemptRow, attempt_id, with_for_update=True)
        if (
            row is None
            or row.state != "RESERVED"
            or row.payload["permit"] != permit.model_dump(mode="json")
            or row.payload["body_hash"] != payload.body_hash
            or not any(
                payload in node.inputs and node.node_id == row.node_id for node in prepared.nodes
            )
        ):
            msg = "vector_dispatch_identity_invalid"
            raise VectorError(msg)
        _transition(row, "SENDING", request_id=row.id)
        session.commit()


def settle_vector(
    db: Database, permit: VectorPermit, attempt_id: str, usage: int, response_id: str
) -> None:
    """Settle validated usage only; excess usage never releases the worst reservation."""
    with db.session() as session:
        lock_budget(db, session)
        authorize_vector(session, permit)
        row = session.get(VectorAttemptRow, attempt_id, with_for_update=True)
        if row is None or row.state != "SENDING" or row.plan_id != permit.plan_id:
            msg = "vector_settlement_identity_invalid"
            raise VectorError(msg)
        if usage < 0 or usage > row.token_bound:
            msg = "vector_usage_exceeded"
            raise VectorError(msg)
        account = session.get(VectorAccountRow, row.plan_id, with_for_update=True)
        if account is None:
            msg = "vector_account_missing"
            raise VectorError(msg)
        policy = row.payload["policy"]
        account.cost_nanos -= row.reserved_nanos - usage * int(policy["nanos_per_token"])
        _transition(row, "SETTLED", usage=usage, response_id=response_id)
        session.commit()


def unknown_vector(db: Database, attempt_id: str, reason: str) -> None:
    """Retain worst occupancy when a dispatched response cannot be trusted."""
    with db.session() as session:
        lock_budget(db, session)
        row = session.get(VectorAttemptRow, attempt_id, with_for_update=True)
        if row is not None and row.state == "SENDING":
            _transition(row, "UNKNOWN", reason=reason)
            session.commit()


def recover_vectors(session: Session, task_id: str) -> None:
    """Recover only after task fencing; never requeue or resend a billed attempt."""
    rows = session.scalars(select(VectorAttemptRow).where(VectorAttemptRow.task_id == task_id))
    for row in rows:
        if row.state == "SENDING":
            _transition(row, "UNKNOWN", reason="vector_lease_lost_after_dispatch")
        elif row.state == "RESERVED":
            account = session.get(VectorAccountRow, row.plan_id, with_for_update=True)
            if account is None:
                msg = "vector_account_missing"
                raise VectorError(msg)
            account.requests -= 1
            account.cost_nanos -= row.reserved_nanos
            _transition(row, "REFUNDED", reason="vector_proven_unsent_after_fencing")


def list_vector_attempts(db: Database, task_id: str) -> tuple[VectorAttempt, ...]:
    """Read restart-stable fake audit summaries without request content."""
    with db.session() as session:
        return tuple(
            _view(row)
            for row in session.scalars(
                select(VectorAttemptRow)
                .where(VectorAttemptRow.task_id == task_id)
                .order_by(VectorAttemptRow.id)
            )
        )


def _account(session: Session, plan_id: str) -> VectorAccountRow:
    row = session.get(VectorAccountRow, plan_id, with_for_update=True)
    if row is None:
        row = VectorAccountRow(plan_id=plan_id, requests=0, cost_nanos=0)
        session.add(row)
    return row
