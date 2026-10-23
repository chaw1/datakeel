# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise human-only approval and execution endpoints from golden scenarios."""

from datakeel.actions.models import ActionPlan, ApprovalDecision, ExecuteRequest
from datakeel.actions.service import approve_plan, execute_plan
from datakeel.core.errors import DatakeelError
from datakeel.core.harness_eval import PlanOperation
from datakeel.core.models import BoundaryModel
from datakeel.storage.database import Database
from datakeel.storage.governance_service import QualityInput, save_quality


class OperationObservation(BoundaryModel):
    """Report a real human-side operation without pre-judging its expected outcome."""

    status: str
    error: str = ""


def apply_operation(
    db: Database, plan: ActionPlan | None, operation: PlanOperation
) -> OperationObservation:
    """Invoke the actual action boundary and retain both success and refusal."""
    if plan is None:
        return OperationObservation(status="MISSING_PLAN", error="No plan was produced")
    try:
        if operation.operation == "change_quality_config":
            save_quality(db, plan.manifest.query.dataset_id or "", QualityInput(min_size_bytes=10))
            return OperationObservation(status="SUCCEEDED")
        if operation.operation in {"approve", "reject"}:
            result = approve_plan(
                db,
                plan.id,
                ApprovalDecision(
                    approve=operation.operation == "approve",
                    plan_digest=plan.plan_digest,
                ),
            )
            return OperationObservation(status=result.status)
        run = execute_plan(
            db,
            plan.id,
            ExecuteRequest(
                plan_digest=plan.plan_digest,
                canonical_params=(
                    operation.canonical_params.root
                    if operation.canonical_params is not None
                    else None
                ),
            ),
        )
        return OperationObservation(status=run.status)
    except DatakeelError as error:
        return OperationObservation(status="REFUSED", error=f"{type(error).__name__}: {error}")
