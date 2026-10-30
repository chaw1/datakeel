# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Leave zero-user mode so the unregistered conversation actor holds no scopes."""

from datakeel.actions import service
from datakeel.actions.models import ActionContext, ExecuteRequest
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument, new_id
from datakeel.storage.database import Database


def register_team(db: Database) -> None:
    """Register one administrator; the Agent's local actor is then not a registered user."""
    plan = service.prepare_action(
        db,
        "manage_users",
        JsonDocument(
            {
                "request_id": new_id(),
                "operation": "create",
                "user_id": "lead",
                "display_name": "Lead",
            }
        ),
        ActionContext(actor="local"),
    )
    run = service.execute_plan(
        db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor="local")
    )
    if run.status != "SUCCEEDED":
        message = f"Team fixture registration failed: {run.error}"
        raise ValidationError(message)
