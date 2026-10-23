# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate immutable execution identity before reading or creating action runs."""

from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan, ActionRun, ExecuteRequest
from datakeel.actions.policy import digest, plan_digest
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError
from datakeel.storage.action_rows import ActionOperationRow, ActionRunRow
from datakeel.storage.action_store import run_view


def validate_execution_request(plan: ActionPlan, request: ExecuteRequest) -> None:
    """Reject wrong digests, callers, or parameters without creating an execution."""
    if request.plan_digest != plan.plan_digest or plan_digest(plan) != plan.plan_digest:
        msg = "Action plan_digest does not match the frozen plan"
        raise ConflictError(msg)
    if request.actor != plan.actor:
        msg = "Action actor does not match the prepared plan"
        raise AuthorizationError(msg)
    if request.operation_id is not None and request.operation_id != plan.operation_id:
        msg = "Operation identity does not match the prepared plan"
        raise ConflictError(msg)
    if request.canonical_params is not None and digest(request.canonical_params) != digest(
        plan.canonical_params
    ):
        msg = "Canonical parameters changed after approval"
        raise ConflictError(msg)


def _request_digest(plan: ActionPlan, request: ExecuteRequest) -> str:
    return digest(
        {
            "plan_id": plan.id,
            "plan_digest": request.plan_digest,
            "actor": request.actor,
            "canonical_params": plan.canonical_params,
        }
    )


def replay_operation(
    session: Session, plan: ActionPlan, request: ExecuteRequest
) -> ActionRun | None:
    """Return a bound run without consuming approval or repeating business effects."""
    if request.operation_id is None:
        return None
    operation = session.get(ActionOperationRow, request.operation_id)
    if operation is None:
        return None
    if (
        operation.plan_id != plan.id
        or operation.actor != request.actor
        or operation.request_digest != _request_digest(plan, request)
    ):
        msg = "Operation identity already binds a different execution request"
        raise ConflictError(msg)
    row = session.get(ActionRunRow, operation.run_id)
    if row is None:
        msg = "Operation's original action run is missing"
        raise NotFoundError(msg)
    return run_view(row)


def remember_operation(
    session: Session, plan: ActionPlan, request: ExecuteRequest, run_id: str
) -> None:
    """Persist the request binding inside the same transaction as its original run."""
    if request.operation_id is not None:
        session.add(
            ActionOperationRow(
                operation_id=request.operation_id,
                plan_id=plan.id,
                actor=request.actor,
                request_digest=_request_digest(plan, request),
                run_id=run_id,
            )
        )
