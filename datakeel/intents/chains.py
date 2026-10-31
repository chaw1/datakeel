# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Advance a confirmed chain step by step as the person who asked for it.

Every target is prepared and executed through the ordinary action services, so receipts,
audit records and lineage are the same as for manual operations. A step that needs a
signature stops the chain until the plan is approved in the approval queue. A failure
stops the chain at that step; running it again skips targets whose plans already executed.
"""

from typing import Literal

from pydantic import JsonValue

from datakeel.actions import service
from datakeel.actions.models import ActionContext, ActionPlan, ActionRun, ExecuteRequest
from datakeel.actions.parameters import PARAMETER_TYPES
from datakeel.core.errors import DatakeelError, ValidationError
from datakeel.core.intent_models import ActionChain, ChainStep
from datakeel.core.models import JsonDocument, LineageEvent, new_id, utcnow
from datakeel.storage.action_store import get_plan
from datakeel.storage.database import Database
from datakeel.storage.intent_chains import claim_chain, plan_runs, save_chain

TargetState = Literal["done", "waiting", "running", "failed"]


def receipt_outputs(receipt: LineageEvent | None) -> dict[str, JsonValue]:
    """Expose receipt outputs as ``<kind>_id``, ``<kind>_ids`` and ``<kind>_version``."""
    values: dict[str, JsonValue] = {}
    for ref in receipt.outputs if receipt else []:
        kind = "package" if ref.asset_type == "task_package" else ref.asset_type or "dataset"
        values.setdefault(f"{kind}_id", ref.asset_id)
        identifiers = values.setdefault(f"{kind}_ids", [])
        if isinstance(identifiers, list):
            identifiers.append(ref.asset_id)
        if ref.version and ref.version.isdigit():
            values.setdefault(f"{kind}_version", int(ref.version))
    return values


def _merge(total: dict[str, JsonValue], extra: dict[str, JsonValue]) -> None:
    for key, value in extra.items():
        current = total.get(key)
        if key.endswith("_ids") and isinstance(current, list) and isinstance(value, list):
            total[key] = [*current, *value]
        else:
            total.setdefault(key, value)


def _nth_of(found: JsonValue, position: JsonValue, reference: str) -> JsonValue:
    """One item of a list output ("the first package the split made"), 1-based."""
    if position is None:
        return found
    if (
        not isinstance(found, list)
        or not isinstance(position, int)
        or not 0 < position <= len(found)
    ):
        message = f"{reference} has no item {position}"
        raise ValidationError(message)
    return found[position - 1]


def resolve_refs(value: JsonValue, chain: ActionChain) -> JsonValue:
    """Replace ``{"$ref": "s1.label_set_id"}`` with the earlier step's receipt value."""
    if isinstance(value, dict) and "$ref" in value:
        step_id, _, output = str(value["$ref"]).partition(".")
        source = next((step for step in chain.steps if step.id == step_id), None)
        if source is None or source.status != "succeeded" or output not in source.outputs:
            message = f"{value['$ref']} is not available from an executed earlier step"
            raise ValidationError(message)
        found = source.outputs[output]
        return _nth_of(found, value.get("$nth"), str(value["$ref"]))
    if isinstance(value, dict):
        return {key: resolve_refs(item, chain) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_refs(item, chain) for item in value]
    return value


def _execute(
    db: Database, chain: ActionChain, plan: ActionPlan
) -> tuple[TargetState, ActionRun | None, str | None]:
    run = service.execute_plan(
        db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor=chain.actor)
    )
    if run.status == "SUCCEEDED":
        return "done", run, None
    if run.status in {"QUEUED", "RUNNING"}:
        return "running", run, None
    return "failed", run, run.reason or run.error or run.status


def _existing(
    db: Database, chain: ActionChain, plan_id: str, *, resuming: bool
) -> tuple[TargetState, ActionRun | None, str | None] | None:
    """Continue an earlier plan for this target, or return None to prepare a new one.

    A rejected plan fails the step; resuming that step asks for a new signature.
    """
    plan = get_plan(db, plan_id)
    runs = plan_runs(db, [plan_id])[plan_id]
    succeeded = next((run for run in runs if run.status == "SUCCEEDED"), None)
    if plan.status == "EXECUTED" and succeeded is not None:
        return "done", succeeded, None
    pending = next((run for run in runs if run.status in {"QUEUED", "RUNNING"}), None)
    if pending is not None:
        return "running", pending, None
    if plan.status == "REJECTED" and not resuming:
        return "failed", None, "The approver rejected this step"
    if plan.status in {"REJECTED", "FAILED"} or plan.expires_at <= utcnow():
        return None
    if plan.status == "APPROVED" or not plan.requires_approval:
        return _execute(db, chain, plan)
    return "waiting", None, None


def _run_target(
    db: Database,
    chain: ActionChain,
    step: ChainStep,
    index: int,
    params: dict[str, JsonValue],
    *,
    resuming: bool,
) -> tuple[TargetState, str, ActionRun | None, str | None]:
    plan_id = step.plan_ids[index] if index < len(step.plan_ids) else ""
    request_id = f"{params.get('request_id', chain.id)}-{step.attempts}-{index}"
    try:
        if plan_id:
            existing = _existing(db, chain, plan_id, resuming=resuming)
            if existing is not None:
                return existing[0], plan_id, existing[1], existing[2]
            request_id = f"{request_id}-{new_id()[:8]}"
        # Prepared exactly like a manual Web or CLI request, so receipts name the person.
        context = ActionContext(actor=chain.actor)
        body = dict(params)
        if "request_id" in PARAMETER_TYPES[step.action].model_fields:
            body["request_id"] = request_id
        plan = service.prepare_action(db, step.action, JsonDocument(body), context)
        if plan.requires_approval:
            return "waiting", plan.id, None, None
        state, run, error = _execute(db, chain, plan)
    except DatakeelError as error:
        return "failed", plan_id, None, str(error)
    return state, plan.id, run, error


def _run_step(db: Database, chain: ActionChain, step: ChainStep) -> ChainStep:
    attempts = step.attempts + 1 if step.status in {"planned", "failed"} else step.attempts
    current = step.model_copy(update={"attempts": attempts, "error": None, "status": "running"})
    try:
        resolved = resolve_refs(dict(step.params), chain)
    except ValidationError as error:
        return current.model_copy(update={"status": "failed", "error": str(error)})
    base = resolved if isinstance(resolved, dict) else {}
    targets = step.items or [{}]
    plan_ids = [*step.plan_ids, *[""] * (len(targets) - len(step.plan_ids))]
    run_ids = [*step.run_ids, *[""] * (len(targets) - len(step.run_ids))]
    outputs: dict[str, JsonValue] = {}
    states: set[TargetState] = set()
    for index, item in enumerate(targets):
        snapshot = current.model_copy(update={"plan_ids": plan_ids})
        state, plan_id, run, error = _run_target(
            db, chain, snapshot, index, {**base, **item}, resuming=step.status == "failed"
        )
        plan_ids[index] = plan_id
        if run is not None:
            run_ids[index] = run.id
            _merge(outputs, receipt_outputs(run.receipt))
        states.add(state)
        if state == "failed":
            return current.model_copy(
                update={
                    "status": "failed",
                    "error": error,
                    "plan_ids": plan_ids,
                    "run_ids": run_ids,
                    "outputs": outputs,
                }
            )
    status = (
        "awaiting_approval"
        if "waiting" in states
        else "running"
        if "running" in states
        else "succeeded"
    )
    return current.model_copy(
        update={"status": status, "plan_ids": plan_ids, "run_ids": run_ids, "outputs": outputs}
    )


def _advance(db: Database, chain: ActionChain) -> ActionChain:
    for position, step in enumerate(chain.steps):
        if step.status == "succeeded":
            continue
        updated = _run_step(db, chain, step)
        steps = [*chain.steps[:position], updated, *chain.steps[position + 1 :]]
        status = "succeeded" if updated.status == "succeeded" else updated.status
        chain = save_chain(db, chain.model_copy(update={"steps": steps, "status": status}))
        if updated.status != "succeeded":
            return chain
    return chain.model_copy(update={"status": "succeeded"})


def advance_chain(db: Database, chain_id: str, actor: str) -> ActionChain:
    """Run or resume a chain as its requester; only Web and CLI entries call this."""
    chain = claim_chain(db, chain_id, actor)
    if chain.status == "succeeded":
        return save_chain(db, chain, release=True)
    try:
        chain = _advance(db, chain)
    finally:
        chain = save_chain(db, chain, release=True)
    return chain
