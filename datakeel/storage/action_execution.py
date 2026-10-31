# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Execute frozen authorized plans once and record failed or denied attempts."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.models import ActionPlan, ActionRun, ExecuteRequest, OperationResult
from datakeel.actions.parameters import ExportParams, parse_params
from datakeel.actions.policy import digest
from datakeel.actions.receipts import receipt
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError, ConflictError, NotFoundError
from datakeel.core.models import JsonDocument, new_id, utcnow
from datakeel.storage.action_access import authorize_plans_in_session
from datakeel.storage.action_approvals import consume_approval
from datakeel.storage.action_deferred import complete_deferred
from datakeel.storage.action_export import export_action, rollback_export
from datakeel.storage.action_locks import lock_action_targets
from datakeel.storage.action_operations import execute_business
from datakeel.storage.action_planning import verify_plan
from datakeel.storage.action_requests import (
    remember_operation,
    replay_operation,
    validate_execution_request,
)
from datakeel.storage.action_rows import ActionRunRow, ApprovalRow
from datakeel.storage.action_store import audit, locked_plan, publish, run_view
from datakeel.storage.data_asset_review import (
    refuse_tool_decision,
    require_independent_reviewer,
)
from datakeel.storage.database import Database
from datakeel.storage.identity_authorization import require_server_scope
from datakeel.storage.production_human import require_production_human

logger = logging.getLogger(__name__)


def _commit_result(
    session: Session, plan: ActionPlan, result: OperationResult, request: ExecuteRequest
) -> ActionRun:
    """Record the attempt, its receipt unless work continues after commit, then commit."""
    status = "QUEUED" if result.task_id else "RUNNING" if result.deferred else "SUCCEEDED"
    row = ActionRunRow(
        id=new_id(),
        plan_id=plan.id,
        action_type=plan.action_type,
        status=status,
        task_id=result.task_id,
    )
    session.add(row)
    session.flush()
    if result.task_id is None and result.deferred is None:
        event = receipt(plan, row.id, result.outputs)
        event = event.model_copy(update={"quality": {**event.quality, "details": result.details}})
        row.receipt = event.model_dump(mode="json")
        row.completed_at = utcnow().timestamp()
        if not (
            plan.action_type in {"import_catalog", "restore_catalog"}
            and result.details.get("status") == "unchanged"
        ):
            publish(session, event)
    audit(session, plan, "EXECUTE", row.status, digest(result.details))
    remember_operation(session, plan, request, row.id)
    session.commit()
    return run_view(row)


def _record_failure(
    db: Database,
    plan_id: str,
    error: Exception,
    request: ExecuteRequest,
    *,
    attempted: bool,
    authorized: bool,
) -> None:
    with db.session() as session:
        lock_action_targets(db, session, plan_id)
        try:
            plan_row, plan = locked_plan(session, plan_id)
        except NotFoundError:
            return
        if replay_operation(session, plan, request) is not None:
            return
        identifier = new_id()
        description = f"{type(error).__name__}: {error}"
        approval = session.scalar(select(ApprovalRow).where(ApprovalRow.plan_id == plan.id))
        denied = (
            not authorized
            and (plan.status != "FAILED" or (approval is not None and approval.consumed))
            and isinstance(error, AuthorizationError | ConflictError)
        )
        status = "DENIED" if denied else "FAILED"
        event = receipt(plan, identifier, [], error=description)
        session.add(
            ActionRunRow(
                id=identifier,
                plan_id=plan.id,
                action_type=plan.action_type,
                status=status,
                error=description,
                receipt=event.model_dump(mode="json"),
                completed_at=utcnow().timestamp(),
            )
        )
        if attempted:
            plan_row.status = "FAILED"
            if approval is not None:
                approval.consumed = True
        audit(session, plan, "EXECUTE", status, description)
        session.flush()
        # A prepared production request can still be signed after an early denied attempt.
        if "request_id" not in plan.canonical_params or status != "DENIED":
            remember_operation(session, plan, request, identifier)
        publish(session, event)
        session.commit()


def _production_request(
    plan: ActionPlan, request: ExecuteRequest, access: AccessContext | None
) -> ExecuteRequest:
    require_production_human(plan, access)
    if "request_id" in plan.canonical_params and request.operation_id is None:
        return request.model_copy(update={"operation_id": plan.operation_id})
    return request


def execute_plan(
    db: Database, plan_id: str, request: ExecuteRequest, *, access: AccessContext | None = None
) -> ActionRun:
    """Atomically revalidate, consume approval, mutate, audit, and publish a receipt."""
    attempted = False
    authorized = False
    result: OperationResult | None = None
    committed = False
    record_attempt = False
    try:
        with db.session() as session:
            lock_action_targets(db, session, plan_id)
            row, plan = locked_plan(session, plan_id)
            request = _production_request(plan, request, access)
            refuse_tool_decision(plan.action_type, access)
            validate_execution_request(plan, request)
            require_server_scope(session, plan, request.actor)
            authorize_plans_in_session(session, (plan,), access, actor=request.actor, record=False)
            prior = replay_operation(session, plan, request)
            if prior is not None:
                authorize_plans_in_session(session, (plan,), access, actor=request.actor)
                session.commit()
                return prior
            record_attempt = True
            consume_approval(session, plan)
            require_independent_reviewer(
                session, plan.action_type, plan.canonical_params, request.actor
            )
            authorized = True
            verify_plan(session, plan, request.plan_digest, request.actor)
            attempted = True
            params = parse_params(plan.action_type, JsonDocument(plan.canonical_params))
            authorize_plans_in_session(session, (plan,), access, actor=request.actor)
            result = (
                export_action(session, plan, params)
                if isinstance(params, ExportParams)
                else execute_business(session, plan)
            )
            row.status = "EXECUTED"
            run = _commit_result(session, plan, result, request)
            committed = True
            if result.deferred is None:
                return run
            deferred = (plan, run.id, result.deferred)
    except Exception as error:
        if not committed:
            rollback_export(result)
        logger.exception("Controlled action failed", extra={"action_id": plan_id})
        if record_attempt:
            _record_failure(db, plan_id, error, request, attempted=attempted, authorized=authorized)
        raise
    # Slow outside work (cloud model calls) runs after the plan's transaction has committed.
    return complete_deferred(db, *deferred)
