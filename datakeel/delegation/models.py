# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen specialist definitions and callback boundaries for delegated execution."""

from pydantic import Field

from datakeel.core.harness_models import ModelCallTrace
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.ontology.tool_models import ToolOutcome


class AgentDefinition(BoundaryModel):
    """Limit a named specialist to declared tools and at most four model turns."""

    name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    description: str = Field(min_length=1, max_length=2000)
    tools: list[str] = Field(min_length=1)
    max_turns: int = Field(default=4, ge=1, le=4)


class DelegateParams(BoundaryModel):
    """Request one registered specialist without accepting capabilities from the caller."""

    agent: str = Field(min_length=1, max_length=64)
    task: str = Field(min_length=1, max_length=8000)


class ChildResult(BoundaryModel):
    """Return primitive events and one conclusion from an isolated child graph."""

    summary: str = ""
    events: list[JsonDocument] = Field(default_factory=list[JsonDocument])
    stop_reason: str | None = None


class DelegationResult(ChildResult):
    """Include the durable tool outcome alongside nested display events."""

    outcome: ToolOutcome


class CallTreeNode(BoundaryModel):
    """Expose hierarchy and measured activity without exposing child capability snapshots."""

    id: str
    parent_id: str | None
    root_id: str
    agent_name: str
    agent_path: str
    depth: int
    parent_tool_call_id: str | None
    tokens: int
    tools: list[str]


class CallTree(BoundaryModel):
    """Return independently auditable nodes and their individual model-call traces."""

    nodes: list[CallTreeNode]
    traces: list[ModelCallTrace]
