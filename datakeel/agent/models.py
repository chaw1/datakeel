# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed conversation views and server-sent events for the public Agent API."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from datakeel.actions.models import ActionPlan
from datakeel.core.agent_models import ChatMessage, ConversationCreate, ToolCall
from datakeel.core.models import BoundaryModel, new_id
from datakeel.core.routing_models import ModelRouteDecision, RouteDecision
from datakeel.ontology.tool_models import ToolOutcome


class AgentEvent(BoundaryModel):
    """Persist one replayable text, tool, plan, receipt, or terminal observation."""

    id: str = Field(default_factory=new_id)
    event: Literal[
        "text",
        "tool_call",
        "tool_result",
        "plan",
        "receipt",
        "stopped",
        "done",
        "route",
    ]
    text: str | None = None
    call: ToolCall | None = None
    outcome: ToolOutcome | None = None
    stop_reason: str | None = None
    route: RouteDecision | None = None
    model_routes: list[ModelRouteDecision] = Field(default_factory=list[ModelRouteDecision])


class ConversationView(BoundaryModel):
    """Expose complete memory with current approval and execution card state."""

    id: str
    actor: Literal["local"] = "local"
    config: ConversationCreate
    created_at: datetime
    messages: list[ChatMessage]
    events: list[AgentEvent]
    turns: int
    pending_plans: list[ActionPlan] = Field(default_factory=list[ActionPlan])
