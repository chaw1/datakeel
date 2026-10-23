# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Confirmation never upgrades failed tools into business executions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.agent.confirm import execute_reversible
from datakeel.ontology.tool_models import ToolCallContext, ToolOutcome
from datakeel.storage.tool_invocations import list_invocations

if TYPE_CHECKING:
    from datakeel.storage.database import Database


def test_confirmation_when_no_successful_plan_exists_does_not_dispatch(db: Database) -> None:
    """Require an actual successful ActionPlan before considering reversible execution."""
    outcome = ToolOutcome(name="quarantine_files", status="FAILED", error="invalid selection")
    assert execute_reversible(db, outcome, ToolCallContext(), dry_run=False) is None
    assert list_invocations(db) == []
