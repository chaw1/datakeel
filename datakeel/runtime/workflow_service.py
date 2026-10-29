# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit workflow starts and signed resumes with one process-released writer per run."""

from collections.abc import Callable, Generator, Iterator
from functools import partial

from datakeel.core.agent_models import ResumeInput
from datakeel.core.errors import ConflictError
from datakeel.core.models import JsonDocument
from datakeel.core.workflow_models import (
    WorkflowCreation,
    WorkflowEvent,
    WorkflowStart,
    WorkflowStep,
)
from datakeel.runtime.workflow_graph import WorkflowGraph
from datakeel.storage.conversation_lock import response_lock
from datakeel.storage.database import Database
from datakeel.storage.identity_sessions import bind_session_actor, require_session_actor
from datakeel.storage.workflow_recovery import begin_resume, finish_resume, interrupt_run
from datakeel.storage.workflow_store import create_run, get_run, list_runs, set_status
from datakeel.workflows.execution import WorkflowHooks
from datakeel.workflows.loader import get_workflow, validate_inputs


def start_workflow(
    db: Database,
    workflow_id: str,
    request: WorkflowStart,
    *,
    hooks: WorkflowHooks | None = None,
    actor: str = "local",
) -> Generator[WorkflowEvent, None, None]:
    """Validate before any start and replay the original run without dispatching a second one."""
    definition = get_workflow(workflow_id)
    checked = request.model_copy(update={"inputs": validate_inputs(definition, request.inputs)})
    with response_lock(db, f"workflow-start:{request.idempotency_key}"):
        run, created = create_run(
            db,
            WorkflowCreation(
                workflow_id=workflow_id,
                definition=JsonDocument.model_validate(definition.model_dump(mode="json")),
                request=checked,
                steps=[WorkflowStep(id=step.id, type=step.type) for step in definition.steps],
            ),
        )
        if created:
            bind_session_actor(db, run.id, actor)
        else:
            require_session_actor(db, run.id, actor)
    if not created:
        yield WorkflowEvent(event="done", run=run)
        return
    with response_lock(db, f"workflow:{run.id}"):
        current = get_run(db, run.id)
        if current.status != "PENDING":
            yield WorkflowEvent(event="done", run=current)
            return
        set_status(db, run.id, "RUNNING")
        graph = WorkflowGraph(db, run.id, hooks)
        yield from _deliver(db, graph, graph.run())


def resume_workflow(
    db: Database,
    run_id: str,
    request: ResumeInput,
    *,
    hooks: WorkflowHooks | None = None,
    actor: str = "local",
) -> Generator[WorkflowEvent, None, None]:
    """Resume only a durable signed gate, serializing callers and preserving its original plan."""
    with response_lock(db, f"workflow:{run_id}"):
        require_session_actor(db, run_id, actor)
        if begin_resume(db, run_id, request):
            yield WorkflowEvent(event="done", run=get_run(db, run_id))
            return
        graph = WorkflowGraph(db, run_id, hooks)
        if get_run(db, run_id).status != "INTERRUPTED":
            graph.restore_pause()
        events = graph.resume(request)
        yield from _deliver(db, graph, events, partial(finish_resume, db, run_id, request))


def _deliver(
    db: Database,
    graph: WorkflowGraph,
    events: Iterator[WorkflowEvent],
    complete: Callable[[], None] | None = None,
) -> Generator[WorkflowEvent, None, None]:
    completed = False
    try:
        yield WorkflowEvent(event="run", run=get_run(db, graph.run_id))
        yield from events
        if complete is not None:
            complete()
        completed = True
        yield WorkflowEvent(event="done", run=get_run(db, graph.run_id))
    finally:
        if not completed and not graph.restore_pause():
            interrupt_run(
                db, graph.run_id, "Client disconnected or workflow stream was interrupted"
            )


def recover_runs(db: Database) -> None:
    """Recover surviving approval gates and interrupt abandoned ordinary runs at process startup."""
    for run in list_runs(db):
        if run.status not in {"PENDING", "RUNNING", "PAUSED"}:
            continue
        try:
            with response_lock(db, f"workflow:{run.id}"):
                if not WorkflowGraph(db, run.id).restore_pause():
                    interrupt_run(db, run.id, "Process restarted before workflow completion")
        except ConflictError:
            # An active process still owns this run; startup must not reclaim it by age.
            continue
