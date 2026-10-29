# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Controlled mutation plans, local user approvals, and durable action receipts."""

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse

from datakeel.actions import service
from datakeel.actions.budget import BudgetRequest, requested_context
from datakeel.actions.models import (
    ActionContext,
    ActionPlan,
    ActionRun,
    ApprovalDecision,
    ExecuteRequest,
)
from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError
from datakeel.core.models import JsonDocument
from datakeel.storage.database import Database
from datakeel.storage.identity_authorization import effective_scopes
from datakeel.storage.training_download import completed_export

router = APIRouter(prefix="/api", tags=["actions"])


def _http_actor(db: Database, request: Request) -> str:
    actor = request.headers.get("X-Datakeel-Actor", "local")
    with db.session() as session:
        return "local" if effective_scopes(session, actor).zero_users else actor


def _require_actor(db: Database, request: Request, actor: str) -> None:
    if actor != _http_actor(db, request):
        msg = "HTTP action decisions must use the request's human identity"
        raise AuthorizationError(msg)


@router.get("/actions/runs")
def action_runs(db: DatabaseDependency, request: Request) -> list[ActionRun]:
    """Read attempts, including DENIED runs with missing/rejected/consumed approval reasons."""
    return service.list_runs(db, access=_read_access(request))


@router.get("/approvals")
def pending_approvals(db: DatabaseDependency, request: Request) -> list[ActionPlan]:
    """Read irreversible or outbound plans awaiting a local user decision."""
    return service.list_approvals(db, access=_read_access(request))


@router.get("/actions/plans/{plan_id}")
def action_plan(plan_id: str, db: DatabaseDependency, request: Request) -> ActionPlan:
    """Read the server-owned frozen plan and its current lifecycle status."""
    return service.get_plan(db, plan_id, access=_read_access(request))


@router.get("/actions/{plan_id}/export")
def download_export(plan_id: str, db: DatabaseDependency, request: Request) -> FileResponse:
    """Download a completed export while rechecking current source export grants."""
    path = completed_export(db, plan_id, access=_read_access(request))
    return FileResponse(path, filename=path.name)


@router.post("/actions/{action_type}/prepare")
def prepare(
    action_type: str,
    body: JsonDocument,
    db: DatabaseDependency,
    request: Request,
    max_objects: Annotated[int | None, Query(ge=1)] = None,
    max_bytes: Annotated[int | None, Query(ge=1)] = None,
) -> ActionPlan:
    """Validate parameters and freeze the exact reviewable impact for the local actor.

    Releases and selected versions accept an explicit object/byte budget up to the
    configured ceiling; the budget is frozen into the plan that the user approves.
    """
    budget = BudgetRequest(max_objects=max_objects, max_bytes=max_bytes)
    context = ActionContext(actor=_http_actor(db, request))
    return service.prepare_action(
        db, action_type, body, requested_context(action_type, budget, context)
    )


@router.post("/approvals/{plan_id}")
def approve(
    plan_id: str, body: ApprovalDecision, db: DatabaseDependency, request: Request
) -> ActionPlan:
    """Approve or reject one displayed plan digest as the local user."""
    _require_actor(db, request, body.actor)
    return service.approve_plan(db, plan_id, body)


@router.post("/actions/{plan_id}/execute")
def execute(
    plan_id: str, body: ExecuteRequest, db: DatabaseDependency, request: Request
) -> ActionRun:
    """Execute once; missing/rejected/consumed approvals record DENIED with a reason.

    A first denied request retains its 403/409 error response. Read its durable run
    through GET /api/actions/runs, or replay its explicit operation_id for that run.
    """
    _require_actor(db, request, body.actor)
    return service.execute_plan(db, plan_id, body)


def _read_access(request: Request) -> AccessContext:
    return AccessContext(
        actor=request.headers.get("X-Datakeel-Actor", "local"), entry="ask", scope="query"
    )
