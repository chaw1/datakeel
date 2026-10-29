# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Execute typed workflow steps through the existing controlled tool and task boundaries."""

from collections.abc import Callable
from time import monotonic, sleep

from pydantic import JsonValue

from datakeel.core.errors import ExecutionError, ValidationError
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.core.workflow_models import WorkflowRun
from datakeel.ontology.tool_models import ToolCallContext, ToolOutcome
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.database import Database
from datakeel.storage.identity_sessions import session_actor
from datakeel.storage.task_queries import query_task
from datakeel.workflows.models import ApprovalStep, BranchStep, OutputStep, ToolStep, WaitStep
from datakeel.workflows.resolver import compare, resolve


class WorkflowHooks(BoundaryModel):
    """Inject polling time and sleep without changing graph scheduling or business facts."""

    clock: Callable[[], float] = monotonic
    sleep: Callable[[float], None] = sleep
    cancelled: Callable[[], bool] = lambda: False

    def check_cancelled(self) -> None:
        """Stop cooperative execution without turning a disconnected stream into task failure."""
        if self.cancelled():
            msg = "Workflow client disconnected"
            raise InterruptedError(msg)


def resolve_value(run: WorkflowRun, value: JsonValue) -> JsonValue:
    """Read completed outputs from authoritative step facts rather than checkpoint objects."""
    outputs = JsonDocument(
        {step.id: step.output for step in run.steps if step.status == "SUCCEEDED"}
    )
    return resolve(value, run.inputs, outputs)


def _context(db: Database, run_id: str) -> ToolCallContext:
    return ToolCallContext(
        actor=session_actor(db, run_id), agent_id="datakeel-workflow", session_id=run_id
    )


def call_tool(db: Database, run: WorkflowRun, step: ToolStep | ApprovalStep) -> ToolOutcome:
    """Prepare one action or read one function with a stable run-scoped invocation identity."""
    name = step.tool if isinstance(step, ToolStep) else step.action
    arguments = JsonDocument.model_validate(resolve_value(run, step.arguments.root))
    outcome = invoke_tool(db, name, arguments, _context(db, run.id), call_id=step.id)
    if outcome.status == "FAILED":
        raise ExecutionError(outcome.error or f"Workflow tool failed: {name}")
    return outcome


def execute_tool(db: Database, run: WorkflowRun, step: ToolStep) -> JsonValue:
    """Automatically execute only reversible plans and publish their durable receipt."""
    outcome = call_tool(db, run, step)
    if outcome.plan is None:
        return outcome.content.root
    plan = outcome.plan
    if plan.requires_approval:
        msg = "An irreversible plan requires an approval step"
        raise ValidationError(msg)
    execution = invoke_tool(
        db,
        "execute_plan",
        JsonDocument(
            {
                "plan_id": plan.id,
                "plan_digest": plan.plan_digest,
                "operation_id": plan.operation_id,
            }
        ),
        _context(db, run.id),
        call_id=plan.operation_id,
    )
    if execution.status == "FAILED" or execution.run is None:
        raise ExecutionError(execution.error or "Workflow action failed")
    return JsonDocument.model_validate(execution.run.model_dump(mode="json")).root


def wait_for_task(
    db: Database, run: WorkflowRun, step: WaitStep, hooks: WorkflowHooks
) -> JsonValue:
    """Poll with an injected deadline; failures never execute later workflow steps."""
    task_id = resolve_value(run, step.task_id)
    if not isinstance(task_id, str):
        msg = "Wait step requires a task identifier"
        raise ValidationError(msg)
    deadline = hooks.clock() + step.timeout_seconds
    while True:
        hooks.check_cancelled()
        task = query_task(db, task_id)
        if task.state == "COMPLETED":
            outcome = invoke_tool(
                db,
                "get_task",
                JsonDocument({"task_id": task_id}),
                _context(db, run.id),
                call_id=step.id,
            )
            return outcome.content.root["data"]
        if task.state in {"FAILED", "CANCELLED"}:
            raise ExecutionError(task.error or "Workflow task failed")
        if hooks.clock() >= deadline:
            msg = (
                f"Task {task_id} timed out after {step.timeout_seconds:g}s; "
                "there may be no worker running. Start one with: datakeel worker"
            )
            raise ExecutionError(msg)
        hooks.sleep(step.poll_interval)


def branch(run: WorkflowRun, step: BranchStep) -> tuple[str, JsonDocument]:
    """Choose one declared edge using only the allowlisted comparator vocabulary."""
    matched = compare(resolve_value(run, step.ref), step.op, resolve_value(run, step.value))
    target = step.then if matched else step.otherwise
    return target, JsonDocument({"matched": matched, "next": target})


def output(run: WorkflowRun, step: OutputStep) -> JsonValue:
    """Render a terminal output from already committed inputs and step outputs."""
    return resolve_value(run, step.value)
