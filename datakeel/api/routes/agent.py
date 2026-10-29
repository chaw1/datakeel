# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Durable local conversations and server-sent model/tool/action events."""

from collections.abc import Generator, Iterator
from itertools import chain
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from datakeel.agent import service
from datakeel.agent.models import AgentEvent, ConversationView
from datakeel.api.dependencies import DatabaseDependency
from datakeel.api.identity_access import http_actor
from datakeel.core.agent_models import (
    ConversationAudit,
    ConversationCreate,
    MessageInput,
    Provider,
    ResumeInput,
)
from datakeel.core.routing_models import RouteDecision
from datakeel.delegation.loader import list_agents
from datakeel.delegation.models import AgentDefinition, CallTree
from datakeel.delegation.tree import call_tree
from datakeel.storage.conversation_authorization import list_audit
from datakeel.storage.identity_sessions import require_session_actor

router = APIRouter(prefix="/api/agent/conversations", tags=["agent"])


class EventStreamResponse(StreamingResponse):
    """Declare the streaming media type alongside its typed event schema."""

    media_type = "text/event-stream"


def get_provider(request: Request) -> Provider | None:
    """Resolve an explicitly injected test provider, otherwise use session settings."""
    return cast("Provider | None", getattr(request.app.state, "agent_provider", None))


ProviderDependency = Annotated[Provider | None, Depends(get_provider)]


@router.post("")
def create(body: ConversationCreate, db: DatabaseDependency, request: Request) -> ConversationView:
    """Create a session with persistent limits and optional dataset context."""
    return service.create_conversation(db, body, actor=http_actor(request))


@router.get("")
def list_all(db: DatabaseDependency, request: Request) -> list[ConversationView]:
    """List recoverable local conversations."""
    return service.list_conversations(db, actor=http_actor(request))


@router.get("/{conversation_id}")
def get(conversation_id: str, db: DatabaseDependency, request: Request) -> ConversationView:
    """Recover all persisted events and current human approval decisions."""
    return service.get_conversation(db, conversation_id, actor=http_actor(request))


@router.get("/{conversation_id}/tree")
def tree(conversation_id: str, db: DatabaseDependency, request: Request) -> CallTree:
    """Read nested specialist sessions and every metered parent and child call."""
    require_session_actor(db, conversation_id, http_actor(request))
    return call_tree(db, conversation_id)


@router.get("/definitions/agents")
def definitions() -> list[AgentDefinition]:
    """List validated specialist contracts bundled with this installation."""
    return list_agents()


def _encode(events: Iterator[AgentEvent], first: AgentEvent | None) -> Iterator[str]:
    for event in chain([first] if first is not None else [], events):
        yield f"id: {event.id}\nevent: {event.event}\ndata: {event.model_dump_json()}\n\n"


@router.post(
    "/{conversation_id}/messages", response_model=AgentEvent, response_class=EventStreamResponse
)
def send(
    conversation_id: str,
    body: MessageInput,
    db: DatabaseDependency,
    provider: ProviderDependency,
    request: Request,
) -> EventStreamResponse:
    """Stream durable events with explicit replay keys and no duplicate execution."""
    stream = cast(
        "Generator[AgentEvent, None, None]",
        service.send_message(
            db, conversation_id, body, provider=provider, actor=http_actor(request)
        ),
    )
    first = next(stream, None)
    return EventStreamResponse(
        _encode(stream, first),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=BackgroundTask(stream.close),
    )


@router.post(
    "/{conversation_id}/resume", response_model=AgentEvent, response_class=EventStreamResponse
)
def resume(
    conversation_id: str,
    body: ResumeInput,
    db: DatabaseDependency,
    provider: ProviderDependency,
    request: Request,
) -> EventStreamResponse:
    """Continue an approved pause without treating caller input as execution authority."""
    stream = cast(
        "Generator[AgentEvent, None, None]",
        service.resume_conversation(
            db, conversation_id, body, provider=provider, actor=http_actor(request)
        ),
    )
    first = next(stream, None)
    return EventStreamResponse(
        _encode(stream, first),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=BackgroundTask(stream.close),
    )


@router.get("/{conversation_id}/audit")
def recovery_audit(
    conversation_id: str, db: DatabaseDependency, request: Request
) -> list[ConversationAudit]:
    """Read persisted resume denials, authorization checks and pause invalidations."""
    require_session_actor(db, conversation_id, http_actor(request))
    return list_audit(db, conversation_id)


@router.get("/{conversation_id}/routes")
def routes(conversation_id: str, db: DatabaseDependency, request: Request) -> list[RouteDecision]:
    """Read persisted workflow suggestions and free-Agent routing decisions."""
    return [
        event.route
        for event in service.get_conversation(db, conversation_id, actor=http_actor(request)).events
        if event.route is not None
    ]
