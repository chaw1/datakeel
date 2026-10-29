# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed invocation contracts shared by the Agent and MCP adapters."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from datakeel.actions.models import ActionPlan, ActionRun
from datakeel.core.models import AssetRef, BoundaryModel, JsonDocument


class ToolCallContext(BoundaryModel):
    """Attribute a local tool request without accepting caller-supplied privileges."""

    actor: str = "local"
    agent_id: str | None = Field(default=None, max_length=128)
    session_id: str | None = Field(default=None, max_length=128)


class ToolOutcome(BoundaryModel):
    """Return replayable data and explicit approval state after one tool invocation."""

    name: str
    status: Literal["SUCCEEDED", "FAILED"]
    content: JsonDocument = Field(default_factory=lambda: JsonDocument({}))
    asset_refs: list[AssetRef] = Field(default_factory=list[AssetRef])
    plan: ActionPlan | None = None
    run: ActionRun | None = None
    requires_approval: bool = False
    error: str | None = None
    invocation_id: str | None = None


class ToolInvocationStart(BoundaryModel):
    """Record the caller and a non-content parameter summary before dispatch."""

    name: str
    arguments_digest: str
    argument_keys: list[str]
    context: ToolCallContext
    asset_refs: list[AssetRef]
    identifier: str | None = None


class ToolInvocation(BoundaryModel):
    """Expose one durable tool span without leaking database rows."""

    id: str
    name: str
    actor: str
    agent_id: str | None
    session_id: str | None
    arguments_digest: str
    argument_keys: list[str]
    asset_refs: list[AssetRef]
    status: Literal["RUNNING", "SUCCEEDED", "FAILED"]
    started_at: datetime
    completed_at: datetime | None
    elapsed_ms: float
    error: str | None


class ApproveToolParams(BoundaryModel):
    """Bind a human decision to one exact frozen plan."""

    plan_id: str
    plan_digest: str
    approve: bool
    reason: str = ""


class ExecuteToolParams(BoundaryModel):
    """Execute the exact previously prepared plan once."""

    plan_id: str
    plan_digest: str
    operation_id: str | None = Field(default=None, min_length=1, max_length=200)
