# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resume controlled effects through their durable plan operation identities."""

from datakeel.actions.models import ExecuteRequest
from datakeel.actions.service import execute_plan, get_plan
from datakeel.ontology.tool_models import ToolOutcome
from datakeel.storage.action_store import list_runs
from datakeel.storage.database import Database


def execute_approved(db: Database, plan_id: str) -> ToolOutcome:
    """Reuse an existing receipt or execute the approved plan with its frozen operation ID."""
    plan = get_plan(db, plan_id)
    run = next(
        (run for run in list_runs(db) if run.plan_id == plan_id and run.status != "DENIED"), None
    )
    if run is None:
        run = execute_plan(
            db,
            plan.id,
            ExecuteRequest(
                plan_digest=plan.plan_digest, operation_id=plan.operation_id, actor=plan.actor
            ),
        )
    return ToolOutcome(
        name="execute_plan",
        status="FAILED" if run.status in {"FAILED", "DENIED"} else "SUCCEEDED",
        run=run,
        error=run.error,
    )
