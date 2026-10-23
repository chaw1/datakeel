# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persisted model traces, immutable price accounting, and tool invocation audit."""

from typing import Literal

from fastapi import APIRouter

from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.harness_models import BudgetAccount, CostSummary, ModelCallTrace
from datakeel.harness import service
from datakeel.ontology.tool_models import ToolInvocation
from datakeel.storage.tool_invocations import list_invocations

router = APIRouter(prefix="/api/harness", tags=["harness"])


@router.get("/traces")
def traces(db: DatabaseDependency, conversation_id: str | None = None) -> list[ModelCallTrace]:
    """Read one persisted row for every attempted provider call."""
    return service.list_traces(db, conversation_id)


@router.get("/costs")
def costs(
    db: DatabaseDependency, group_by: Literal["conversation", "day", "model"] = "conversation"
) -> list[CostSummary]:
    """Group recorded costs without repricing historical calls."""
    return service.summarize_costs(db, group_by)


@router.get("/budgets")
def budgets(db: DatabaseDependency) -> list[BudgetAccount]:
    """Inspect durable used and reserved session/day limits."""
    return service.list_accounts(db)


@router.get("/invocations")
def invocations(db: DatabaseDependency, session_id: str | None = None) -> list[ToolInvocation]:
    """Inspect summaries and extracted asset identities without duplicating payloads."""
    return list_invocations(db, session_id)
