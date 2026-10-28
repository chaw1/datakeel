# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Dispatch schema-validated read tools and controlled action plans with durable audit."""

import logging
from time import perf_counter

from pydantic import ValidationError as ModelValidationError

from datakeel.actions import service
from datakeel.actions.models import ActionContext, ActionPlan, ApprovalDecision, ExecuteRequest
from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.actions.policy import digest
from datakeel.actions.references import plan_refs
from datakeel.core.data_asset_models import AccessContext, AccessEntry
from datakeel.core.errors import AuthorizationError, DatakeelError, NotFoundError
from datakeel.core.models import JsonDocument
from datakeel.ontology.functions import PARAMETER_MODELS, invoke_function
from datakeel.ontology.tool_models import (
    ApproveToolParams,
    ExecuteToolParams,
    ToolCallContext,
    ToolInvocationStart,
    ToolOutcome,
)
from datakeel.ontology.tool_refs import argument_refs, extract_refs, reconcile_refs
from datakeel.storage.data_asset_access import require_access
from datakeel.storage.database import Database
from datakeel.storage.tool_invocations import (
    begin_invocation,
    finish_invocation,
    invocation_identity,
    replay_invocation,
)

logger = logging.getLogger(__name__)


def _plan_outcome(name: str, plan: ActionPlan) -> ToolOutcome:
    return ToolOutcome(
        name=name,
        status="SUCCEEDED",
        plan=plan,
        requires_approval=plan.requires_approval,
        asset_refs=plan_refs(plan),
        content=JsonDocument.model_validate(plan.model_dump(mode="json")),
    )


def _control(
    db: Database, name: str, arguments: JsonDocument, access: AccessContext
) -> ToolOutcome:
    if name == "approve_plan":
        approval = ApproveToolParams.model_validate(arguments.root)
        plan = service.approve_plan(
            db,
            approval.plan_id,
            ApprovalDecision(
                plan_digest=approval.plan_digest,
                approve=approval.approve,
                reason=approval.reason,
                actor=access.actor,
            ),
            access=access,
        )
        return _plan_outcome(name, plan)
    if name == "execute_plan":
        request = ExecuteToolParams.model_validate(arguments.root)
        run = service.execute_plan(
            db,
            request.plan_id,
            ExecuteRequest(
                plan_digest=request.plan_digest,
                operation_id=request.operation_id,
                actor=access.actor,
            ),
            access=access,
        )
        return ToolOutcome(
            name=name,
            status="FAILED" if run.status in {"FAILED", "DENIED"} else "SUCCEEDED",
            run=run,
            error=run.error,
            content=JsonDocument.model_validate(run.model_dump(mode="json")),
        )
    msg = f"Unknown tool: {name}"
    raise NotFoundError(msg)


def _dispatch(
    db: Database, name: str, arguments: JsonDocument, context: ToolCallContext, entry: AccessEntry
) -> ToolOutcome:
    if name in PARAMETER_MODELS:
        result = invoke_function(
            db,
            name,
            arguments,
            access=AccessContext(actor=context.actor, entry=entry, scope="query"),
        )
        return ToolOutcome(
            name=name,
            status="SUCCEEDED",
            asset_refs=result.asset_refs,
            content=JsonDocument.model_validate(
                result.model_dump(
                    mode="json", exclude={"skipped"} if result.skipped is None else None
                )
            ),
        )
    if name in PARAMETER_TYPES:
        plan = service.prepare_action(
            db,
            name,
            arguments,
            ActionContext(**context.model_dump()),
            access=AccessContext(actor=context.actor, entry=entry, scope="query"),
        )
        return _plan_outcome(name, plan)
    return _control(
        db, name, arguments, AccessContext(actor=context.actor, entry=entry, scope="query")
    )


def _finish(
    db: Database, outcome: ToolOutcome, arguments: JsonDocument, identifier: str, started: float
) -> ToolOutcome:
    result = outcome.model_copy(
        update={
            "invocation_id": identifier,
            "asset_refs": reconcile_refs(
                outcome.asset_refs,
                argument_refs(outcome.name, arguments.root) + extract_refs(outcome.content.root),
            ),
        }
    )
    finish_invocation(db, result, (perf_counter() - started) * 1000)
    return result


def _replay_access(
    db: Database, previous: ToolOutcome, context: ToolCallContext, entry: AccessEntry
) -> ToolOutcome:
    caller = AccessContext(actor=context.actor, entry=entry, scope="query")
    try:
        if previous.plan is not None:
            service.authorize_plan(db, previous.plan, caller)
        elif previous.run is not None:
            service.authorize_run(db, previous.run, caller)
        elif previous.name in PARAMETER_MODELS and previous.status == "SUCCEEDED":
            require_access(db, tuple(previous.asset_refs), caller)
    except AuthorizationError as error:
        return ToolOutcome(name=previous.name, status="FAILED", error=str(error))
    return previous


def invoke_tool(
    db: Database,
    name: str,
    arguments: JsonDocument,
    context: ToolCallContext,
    *,
    call_id: str | None = None,
    entry: AccessEntry = "agent",
) -> ToolOutcome:
    """Persist every attempt; action tools only prepare and require explicit execution."""
    started = perf_counter()
    identity = invocation_identity(context.session_id, call_id)
    previous = replay_invocation(db, identity, name, digest(arguments.root))
    if previous is not None:
        return _replay_access(db, previous, context, entry)
    identifier = begin_invocation(
        db,
        ToolInvocationStart(
            name=name,
            arguments_digest=digest(arguments.root),
            argument_keys=sorted(arguments.root),
            context=context,
            asset_refs=argument_refs(name, arguments.root),
            identifier=identity,
        ),
    )
    try:
        outcome = _dispatch(db, name, arguments, context, entry)
    except (DatakeelError, ModelValidationError) as error:
        outcome = ToolOutcome(name=name, status="FAILED", error=str(error))
    except Exception as error:
        logger.exception("Tool dispatch failed", extra={"session_id": context.session_id})
        _finish(
            db,
            ToolOutcome(name=name, status="FAILED", error=f"{type(error).__name__}: {error}"),
            arguments,
            identifier,
            started,
        )
        raise
    return _finish(db, outcome, arguments, identifier, started)
