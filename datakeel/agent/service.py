# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Public conversation creation, replay, and controlled response streaming."""

from collections.abc import Generator, Iterator
from contextlib import closing

from datakeel.agent.factory import provider_session
from datakeel.agent.memory import close_interrupted, conversation_view, conversation_views
from datakeel.agent.models import AgentEvent, ConversationView
from datakeel.agent.providers import FakeProvider
from datakeel.core.agent_models import (
    ConversationCreate,
    ConversationDefaults,
    MessageInput,
    Provider,
    ResumeInput,
)
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument
from datakeel.core.settings import get_settings
from datakeel.dataset_store.dataset_service import get_dataset
from datakeel.delegation.loader import list_agents
from datakeel.intents.turns import planner_events
from datakeel.routing.config import load_config, openai_host, route_problem
from datakeel.routing.service import model_decisions, route_message
from datakeel.runtime.graph import AgentGraph
from datakeel.storage import conversation_store as memory
from datakeel.storage.conversation_lock import response_lock
from datakeel.storage.conversation_resume import abandoned_token, begin_resume
from datakeel.storage.data_asset_context import read_agent_histories, require_agent_history
from datakeel.storage.database import Database
from datakeel.storage.identity_sessions import (
    bind_session_actor,
    require_session_actor,
    session_actors,
)


def create_conversation(
    db: Database, request: ConversationCreate, *, actor: str = "local"
) -> ConversationView:
    """Validate an optional workspace and persist the new session configuration."""
    load_config()
    list_agents()
    if request.dataset_id is not None:
        get_dataset(db, request.dataset_id)
    conversation = memory.create(db, request)
    bind_session_actor(db, conversation.id, actor)
    return conversation_view(db, conversation)


def get_conversation(
    db: Database, conversation_id: str, *, actor: str | None = None
) -> ConversationView:
    """Read all messages and hydrate plan cards with the latest human decisions."""
    if actor is not None:
        require_session_actor(db, conversation_id, actor)
    return conversation_view(db, read_agent_histories(db, [memory.get(db, conversation_id)])[0])


def list_conversations(db: Database, *, actor: str | None = None) -> list[ConversationView]:
    """List persisted local conversations with complete transcript views."""
    conversations = memory.list_all(db)
    actors = session_actors(db, [item.id for item in conversations]) if actor is not None else {}
    selected = [item for item in conversations if actor is None or actors[item.id] == actor]
    return conversation_views(db, read_agent_histories(db, selected))


def send_message(
    db: Database,
    conversation_id: str,
    request: MessageInput,
    *,
    provider: Provider | None = None,
    actor: str | None = None,
) -> Iterator[AgentEvent]:
    """Stream durable events; replay a completed request without executing it again."""
    yield from _respond(db, conversation_id, request, provider, actor)


def resume_conversation(
    db: Database,
    conversation_id: str,
    request: ResumeInput,
    *,
    provider: Provider | None = None,
    actor: str | None = None,
) -> Iterator[AgentEvent]:
    """Resume a signed pause with a separate response lease and no synthetic user turn."""
    yield from _respond(db, conversation_id, request, provider, actor)


def _respond(
    db: Database,
    session_id: str,
    request: MessageInput | ResumeInput,
    provider: Provider | None,
    actor: str | None,
) -> Iterator[AgentEvent]:
    with response_lock(db, session_id):
        if actor is not None:
            require_session_actor(db, session_id, actor)
        if token := abandoned_token(db, session_id):
            close_interrupted(db, session_id, token)
            memory.finish(db, session_id, token, completed=False)
        lease = (
            memory.begin(db, session_id, request)
            if isinstance(request, MessageInput)
            else begin_resume(db, session_id, request)
        )
        with closing(_response_events(db, session_id, lease.token, provider, request)) as events:
            if lease.replay is not None:
                require_agent_history(db, session_id)
                yield from (AgentEvent.model_validate(document.root) for document in lease.replay)
                return
            completed = False
            try:
                for event in events:
                    memory.append(
                        db,
                        session_id,
                        lease.token,
                        event=JsonDocument.model_validate(event.model_dump(mode="json")),
                    )
                    if event.event == "done" and event.agent_path == "main":
                        completed = True
                    yield event
            finally:
                if not completed:
                    close_interrupted(db, session_id, lease.token)
                memory.finish(db, session_id, lease.token, completed=completed)


def _response_events(
    db: Database,
    conversation_id: str,
    token: str,
    provider: Provider | None,
    request: MessageInput | ResumeInput,
) -> Generator[AgentEvent]:
    conversation = memory.get(db, conversation_id)
    graph = AgentGraph(db, conversation_id, token, provider)
    events = graph.resume(request) if isinstance(request, ResumeInput) else graph.run()
    route = None
    try:
        with provider_session(conversation.config, provider) as chosen:
            graph.provider = chosen
            if isinstance(request, MessageInput):
                offline = isinstance(chosen, FakeProvider)
                route = route_message(db, conversation, chosen, offline_classifier=offline)
            graph.workflow_confirmation_required = route is not None and route.requires_confirmation
            planned = (
                planner_events(db, conversation, chosen, request.context, token, mode=request.mode)
                if isinstance(request, MessageInput)
                and route is not None
                and route.workflow_id is None
                else None
            )
            yield from events if planned is None else planned
            if route is not None and route.workflow_id is not None:
                yield AgentEvent(event="route", route=route)
    except ValidationError as error:
        yield AgentEvent(event="stopped", stop_reason="configuration_error", text=str(error))
    yield AgentEvent(
        event="done",
        route=route if route is not None and route.workflow_id is None else None,
        model_routes=model_decisions(db, conversation_id, conversation.turns),
        used_memory_ids=graph.used_memories(),
    )


def conversation_defaults() -> ConversationDefaults:
    """Offer routed models when configured, otherwise the offline demo with its reason."""
    settings = get_settings()
    problem = route_problem(settings)
    if problem is not None:
        endpoint = openai_host(settings) if problem == "unrouted_endpoint" else None
        return ConversationDefaults(
            provider="fake", model="fake-demo", problem=problem, endpoint=endpoint
        )
    provider = "openai" if settings.openai_api_key is not None else "anthropic"
    return ConversationDefaults(provider=provider, model="auto")
