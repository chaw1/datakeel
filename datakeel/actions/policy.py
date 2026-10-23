# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Pure canonical digest and authorization rules for controlled execution."""

import hashlib
import json

from datakeel.actions.models import ActionPlan
from datakeel.actions.registry import action_definition
from datakeel.core.errors import AuthorizationError, BudgetError, ConflictError, ValidationError
from datakeel.core.models import utcnow


def digest(value: object) -> str:
    """Hash stable JSON, rejecting nonfinite values and ambiguous formatting."""
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def plan_digest(plan: ActionPlan) -> str:
    """Bind executable fields while preserving digests of older operation-less plans."""
    excluded = {"plan_digest", "status"}
    if plan.operation_id is None:
        excluded.add("operation_id")
    return digest(plan.model_dump(mode="json", exclude=excluded))


def authorize(plan: ActionPlan, actor: str) -> None:
    """Enforce actor, declared scope, budget, expiry, and complete selection."""
    definition = action_definition(plan.action_type)
    if actor != plan.actor:
        msg = "Action actor does not match the prepared plan"
        raise AuthorizationError(msg)
    if "*" not in plan.context.scopes and definition.auth_scope not in plan.context.scopes:
        msg = f"Missing action scope: {definition.auth_scope}"
        raise AuthorizationError(msg)
    if (
        plan.impact.object_count > plan.context.max_objects
        or plan.impact.total_bytes > plan.context.max_bytes
    ):
        msg = "Action impact exceeds the authorized object or byte budget"
        raise BudgetError(msg)
    if plan.expires_at <= utcnow():
        msg = "Action plan has expired"
        raise ConflictError(msg)
    if plan.manifest.truncated:
        msg = "Action selection is truncated; narrow the selection or raise its limit"
        raise ValidationError(msg)
