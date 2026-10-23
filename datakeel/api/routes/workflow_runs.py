# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit workflow execution, synchronous snapshots and queryable recovery audit."""

from threading import Event
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request

from datakeel.api.dependencies import DatabaseDependency
from datakeel.api.routes.agent import EventStreamResponse
from datakeel.api.workflow_stream import WorkflowStreamResponse
from datakeel.core.agent_models import ResumeInput
from datakeel.core.workflow_models import WorkflowAudit, WorkflowEvent, WorkflowRun, WorkflowStart
from datakeel.runtime.workflow_service import resume_workflow, start_workflow
from datakeel.storage.workflow_recovery import list_audit
from datakeel.storage.workflow_store import get_run, list_runs
from datakeel.workflows.execution import WorkflowHooks
from datakeel.workflows.loader import get_workflow, list_workflows
from datakeel.workflows.models import WorkflowDefinition

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def get_hooks(request: Request) -> WorkflowHooks | None:
    """Resolve an explicit local polling test hook; production uses real clock and sleep."""
    return cast("WorkflowHooks | None", getattr(request.app.state, "workflow_hooks", None))


HooksDependency = Annotated[WorkflowHooks | None, Depends(get_hooks)]


@router.get("")
def definitions() -> list[WorkflowDefinition]:
    """List validated bundled workflows and their form input declarations."""
    return list_workflows()


@router.get("/runs")
def runs(db: DatabaseDependency) -> list[WorkflowRun]:
    """List execution history, keeping each explicit run independent of conversations."""
    return list_runs(db)


@router.get("/runs/{run_id}")
def run(run_id: str, db: DatabaseDependency) -> WorkflowRun:
    """Read a full durable timeline after a stream disconnect or page reload."""
    return get_run(db, run_id)


@router.get("/runs/{run_id}/audit")
def audit(run_id: str, db: DatabaseDependency) -> list[WorkflowAudit]:
    """Inspect signed-resume authorization and interrupted-run evidence."""
    return list_audit(db, run_id)


def _cancellable(hooks: WorkflowHooks | None, cancelled: Event) -> WorkflowHooks:
    if hooks is None:

        def sleep(seconds: float) -> None:
            cancelled.wait(seconds)

        return WorkflowHooks(sleep=sleep, cancelled=cancelled.is_set)
    base = hooks or WorkflowHooks()
    return base.model_copy(update={"cancelled": lambda: cancelled.is_set() or base.cancelled()})


@router.post(
    "/runs/{run_id}/resume", response_model=WorkflowEvent, response_class=EventStreamResponse
)
def resume(
    run_id: str, body: ResumeInput, db: DatabaseDependency, hooks: HooksDependency
) -> EventStreamResponse:
    """Continue after a human decision; the request body itself grants no authority."""
    cancelled = Event()
    return WorkflowStreamResponse(
        resume_workflow(db, run_id, body, hooks=_cancellable(hooks, cancelled)), cancelled
    )


@router.get("/{workflow_id}")
def definition(workflow_id: str) -> WorkflowDefinition:
    """Read one validated workflow's schema, steps and routing vocabulary."""
    return get_workflow(workflow_id)


@router.post(
    "/{workflow_id}/runs", response_model=WorkflowEvent, response_class=EventStreamResponse
)
def start(
    workflow_id: str, body: WorkflowStart, db: DatabaseDependency, hooks: HooksDependency
) -> EventStreamResponse:
    """Start an explicitly requested workflow once and stream its durable snapshots."""
    cancelled = Event()
    return WorkflowStreamResponse(
        start_workflow(db, workflow_id, body, hooks=_cancellable(hooks, cancelled)), cancelled
    )
