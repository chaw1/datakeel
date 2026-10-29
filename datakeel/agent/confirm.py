# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep irreversible approval exclusively in the human interaction layer."""

from datakeel.actions.production_language import PRODUCTION_LANGUAGE
from datakeel.core.models import JsonDocument
from datakeel.ontology.tool_models import ToolCallContext, ToolOutcome
from datakeel.ontology.tooling import invoke_tool
from datakeel.storage.database import Database


def execute_reversible(
    db: Database, outcome: ToolOutcome, context: ToolCallContext, *, dry_run: bool
) -> ToolOutcome | None:
    """Execute only a successful reversible plan after checking authoritative plan policy."""
    plan = outcome.plan
    if outcome.status != "SUCCEEDED" or plan is None or plan.requires_approval or dry_run:
        return None
    if plan.action_type in PRODUCTION_LANGUAGE:
        return None
    return invoke_tool(
        db,
        "execute_plan",
        JsonDocument(
            {
                "plan_id": plan.id,
                "plan_digest": plan.plan_digest,
                "operation_id": plan.operation_id,
            }
        ),
        context,
        call_id=plan.operation_id,
    )
