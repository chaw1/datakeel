# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compile validated workflow steps into a synchronous persistent graph."""

from collections.abc import Iterator
from functools import partial
from typing import TYPE_CHECKING, cast

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import JsonValue
from pydantic import ValidationError as ModelValidationError

from datakeel.agent.recovery import execute_approved
from datakeel.core.agent_models import ResumeInput
from datakeel.core.errors import DatakeelError, ExecutionError, ValidationError
from datakeel.core.models import BoundaryModel, JsonDocument, utcnow
from datakeel.core.workflow_models import WorkflowEvent, WorkflowRun, WorkflowStep
from datakeel.runtime import DURABILITY
from datakeel.runtime.saver import SQLAlchemySaver
from datakeel.runtime.tracing import tracing_disabled
from datakeel.storage.database import Database
from datakeel.storage.workflow_recovery import authorize_resume
from datakeel.storage.workflow_store import get_record, get_run, save_step, set_status
from datakeel.workflows import execution
from datakeel.workflows.execution import WorkflowHooks
from datakeel.workflows.models import (
    ApprovalStep,
    BranchStep,
    OutputStep,
    Step,
    ToolStep,
    WaitStep,
    WorkflowDefinition,
)

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig


class WorkflowState(BoundaryModel):
    """Persist only primitive routing identifiers, never credentials or business objects."""

    step_id: str = ""
    plan_id: str = ""
    next_node: str = "__end__"


def approval_gate(state: WorkflowState) -> dict[str, str]:
    """Only pause; replay of this node performs no business writes or action dispatch."""
    interrupt(state.plan_id)
    return {}


def _route(state: WorkflowState) -> str:
    return state.next_node


class WorkflowGraph:
    """Bind a frozen definition to its run's independent fact store and checkpoint thread."""

    def __init__(self, db: Database, run_id: str, hooks: WorkflowHooks | None = None) -> None:
        """Compile each step and split irreversible actions into prepare, gate and execute."""
        self.db, self.run_id, self.hooks = db, run_id, hooks or WorkflowHooks()
        self.definition = WorkflowDefinition.model_validate(get_record(db, run_id).definition.root)
        self.steps = {step.id: step for step in self.definition.steps}
        self.config: RunnableConfig = {
            "configurable": {"thread_id": f"workflow:{run_id}"},
            "recursion_limit": len(self.steps) * 3 + 20,
        }
        builder = StateGraph(WorkflowState)
        builder.add_node("approval_gate", approval_gate)
        builder.add_node("execute_approval", self._execute)
        builder.add_edge("approval_gate", "execute_approval")
        builder.add_conditional_edges("execute_approval", _route)
        for step in self.definition.steps:
            builder.add_node(f"step__{step.id}", partial(self._node, step))
            builder.add_conditional_edges(f"step__{step.id}", _route)
        builder.add_edge(START, f"step__{self.definition.entry}")
        self.graph = builder.compile(checkpointer=SQLAlchemySaver(db))

    def pending_plan(self) -> str:
        """Recognize only a persisted interrupt or its unfinished authorized execute node."""
        snapshot = self.graph.get_state(self.config)
        if not snapshot.interrupts and "execute_approval" not in snapshot.next:
            return ""
        return WorkflowState.model_validate(snapshot.values).plan_id

    def run(self) -> Iterator[WorkflowEvent]:
        """Start a new graph using JSON-safe primitive state."""
        return self._stream(cast("WorkflowState", WorkflowState().model_dump()))

    def resume(self, request: ResumeInput) -> Iterator[WorkflowEvent]:
        """Authorize against signed facts before constructing the graph continuation."""
        authorize_resume(self.db, self.run_id, request.plan_id, self.pending_plan())
        snapshot = self.graph.get_state(self.config)
        values = {item.id: request.plan_id for item in snapshot.interrupts}
        command: Command[str] | None = Command(resume=values) if values else None
        return self._stream(command)

    def restore_pause(self) -> bool:
        """Publish an interrupted gate after its checkpoint survived a process crash."""
        if get_run(self.db, self.run_id).status not in {"PENDING", "RUNNING", "PAUSED"}:
            return False
        plan_id = self.pending_plan()
        if not plan_id:
            return False
        state = WorkflowState.model_validate(self.graph.get_state(self.config).values)
        step = self._step(state.step_id)
        run = get_run(self.db, self.run_id)
        if run.status == "PAUSED" and run.pending_plan_id == plan_id and step.status == "PAUSED":
            return True
        save_step(self.db, self.run_id, step.model_copy(update={"status": "PAUSED"}))
        set_status(self.db, self.run_id, "PAUSED", plan_id=plan_id)
        return True

    def _stream(self, value: WorkflowState | Command[str] | None) -> Iterator[WorkflowEvent]:
        with tracing_disabled():
            for update in self.graph.stream(
                value, self.config, stream_mode="custom", durability=DURABILITY
            ):
                yield WorkflowEvent.model_validate_json(cast("str", update))
            if self.graph.get_state(self.config).interrupts:
                self.restore_pause()
                yield WorkflowEvent(event="run", run=get_run(self.db, self.run_id))

    def _step(self, identity: str) -> WorkflowStep:
        return next(step for step in get_run(self.db, self.run_id).steps if step.id == identity)

    def _emit(self, identity: str) -> None:
        event = WorkflowEvent(event="step", run=get_run(self.db, self.run_id), step_id=identity)
        get_stream_writer()(event.model_dump_json())

    def _begin(self, identity: str) -> None:
        self.hooks.check_cancelled()
        step = self._step(identity)
        save_step(
            self.db,
            self.run_id,
            step.model_copy(
                update={
                    "status": "RUNNING",
                    "started_at": step.started_at or utcnow(),
                    "error": None,
                }
            ),
        )
        self._emit(identity)

    def _finish(self, identity: str, output: JsonValue) -> None:
        step = self._step(identity)
        save_step(
            self.db,
            self.run_id,
            step.model_copy(
                update={
                    "status": "SUCCEEDED",
                    "output": output,
                    "finished_at": utcnow(),
                }
            ),
        )
        self._emit(identity)

    def _failure(self, identity: str, error: str) -> dict[str, str]:
        step = self._step(identity)
        save_step(
            self.db,
            self.run_id,
            step.model_copy(
                update={
                    "status": "FAILED",
                    "error": error,
                    "finished_at": utcnow(),
                }
            ),
        )
        set_status(self.db, self.run_id, "FAILED", error=error)
        self._emit(identity)
        return {"step_id": identity, "next_node": END}

    def _node(self, step: Step, state: WorkflowState) -> dict[str, str]:
        del state
        self._begin(step.id)
        try:
            run = get_run(self.db, self.run_id)
            if isinstance(step, ApprovalStep):
                return self._prepare(run, step)
            target, result = self._evaluate(run, step)
            self._finish(step.id, result)
            if isinstance(step, OutputStep):
                set_status(self.db, self.run_id, "SUCCEEDED")
        except (DatakeelError, ModelValidationError, ValueError) as error:
            return self._failure(step.id, str(error))
        else:
            return {"step_id": step.id, "next_node": target}

    def _evaluate(
        self, run: WorkflowRun, step: ToolStep | WaitStep | BranchStep | OutputStep
    ) -> tuple[str, JsonValue]:
        if isinstance(step, ToolStep):
            return f"step__{step.next}", execution.execute_tool(self.db, run, step)
        if isinstance(step, WaitStep):
            return f"step__{step.next}", execution.wait_for_task(self.db, run, step, self.hooks)
        if isinstance(step, BranchStep):
            target, result = execution.branch(run, step)
            return f"step__{target}", result.root
        return END, execution.output(run, step)

    def _prepare(self, run: WorkflowRun, step: ApprovalStep) -> dict[str, str]:
        outcome = execution.call_tool(self.db, run, step)
        if outcome.plan is None or not outcome.plan.requires_approval:
            msg = "Approval step did not prepare an irreversible plan"
            raise ValidationError(msg)
        save_step(
            self.db, run.id, self._step(step.id).model_copy(update={"plan_id": outcome.plan.id})
        )
        return {"step_id": step.id, "plan_id": outcome.plan.id, "next_node": "approval_gate"}

    def _execute(self, state: WorkflowState) -> dict[str, str]:
        self._begin(state.step_id)
        try:
            step = self.steps[state.step_id]
            if not isinstance(step, ApprovalStep):
                msg = "Checkpoint does not identify an approval step"
                raise ValidationError(msg)
            outcome = execute_approved(self.db, state.plan_id)
            if outcome.status == "FAILED" or outcome.run is None:
                raise ExecutionError(outcome.error or "Approved action failed")
            self._finish(
                state.step_id, JsonDocument.model_validate(outcome.run.model_dump(mode="json")).root
            )
            set_status(self.db, self.run_id, "RUNNING")
        except (DatakeelError, ModelValidationError, ValueError) as error:
            return self._failure(state.step_id, str(error))
        else:
            return {"step_id": state.step_id, "next_node": f"step__{step.next}"}
