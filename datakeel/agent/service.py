# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Public conversation creation, replay, and controlled response streaming."""

from collections.abc import Iterator

from datakeel.agent.factory import provider_session
from datakeel.agent.memory import close_interrupted, conversation_view
from datakeel.agent.models import AgentEvent, ConversationView
from datakeel.core.agent_models import (
    ConversationCreate,
    ConversationLease,
    MessageInput,
    Provider,
    ResumeInput,
)
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument
from datakeel.delegation.loader import list_agents
from datakeel.routing.config import load_config
from datakeel.routing.service import model_decisions, route_message
from datakeel.runtime.graph import AgentGraph
from datakeel.storage import conversation_store as memory
from datakeel.storage.conversation_lock import response_lock
from datakeel.storage.conversation_resume import abandoned_token, begin_resume
from datakeel.storage.data_asset_context import read_agent_histories, require_agent_history
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import get_dataset


def create_conversation(db: Database, request: ConversationCreate) -> ConversationView:
    """Validate an optional workspace and persist the new session configuration."""
    load_config()
    list_agents()
    if request.dataset_id is not None:
        get_dataset(db, request.dataset_id)
    return conversation_view(db, memory.create(db, request))


def get_conversation(db: Database, conversation_id: str) -> ConversationView:
    """Read all messages and hydrate plan cards with the latest human decisions."""
    return conversation_view(db, read_agent_histories(db, [memory.get(db, conversation_id)])[0])


def list_conversations(db: Database) -> list[ConversationView]:
    """List persisted local conversations with complete transcript views."""
    return [conversation_view(db, item) for item in read_agent_histories(db, memory.list_all(db))]


def send_message(
    db: Database,
    conversation_id: str,
    request: MessageInput,
    *,
    provider: Provider | None = None,
) -> Iterator[AgentEvent]:
    """Stream durable events; replay a completed request without executing it again."""
    with response_lock(db, conversation_id):
        _recover_lease(db, conversation_id)
        lease = memory.begin(db, conversation_id, request)
        yield from _deliver(
            db, conversation_id, lease, _response_events(db, conversation_id, lease.token, provider)
        )


def resume_conversation(
    db: Database,
    conversation_id: str,
    request: ResumeInput,
    *,
    provider: Provider | None = None,
) -> Iterator[AgentEvent]:
    """Resume a signed pause with a separate response lease and no synthetic user turn."""
    with response_lock(db, conversation_id):
        _recover_lease(db, conversation_id)
        lease = begin_resume(db, conversation_id, request)
        yield from _deliver(
            db,
            conversation_id,
            lease,
            _response_events(db, conversation_id, lease.token, provider, request),
        )


def _recover_lease(db: Database, conversation_id: str) -> None:
    token = abandoned_token(db, conversation_id)
    if token:
        close_interrupted(db, conversation_id, token)
        memory.finish(db, conversation_id, token, completed=False)


def _deliver(
    db: Database, conversation_id: str, lease: ConversationLease, events: Iterator[AgentEvent]
) -> Iterator[AgentEvent]:
    if lease.replay is not None:
        require_agent_history(db, conversation_id)
        yield from (AgentEvent.model_validate(document.root) for document in lease.replay)
        return
    completed = False
    try:
        for event in events:
            memory.append(
                db,
                conversation_id,
                lease.token,
                event=JsonDocument.model_validate(event.model_dump(mode="json")),
            )
            if event.event == "done" and event.agent_path == "main":
                completed = True
            yield event
    finally:
        if not completed:
            close_interrupted(db, conversation_id, lease.token)
        memory.finish(db, conversation_id, lease.token, completed=completed)


def _response_events(
    db: Database,
    conversation_id: str,
    token: str,
    provider: Provider | None,
    resume: ResumeInput | None = None,
) -> Iterator[AgentEvent]:
    conversation = memory.get(db, conversation_id)
    config = conversation.config
    graph = AgentGraph(db, conversation_id, token, provider)
    events = graph.run() if resume is None else graph.resume(resume)
    route = None
    try:
        with provider_session(config, provider) as selected:
            graph.provider = selected
            route = route_message(db, conversation, selected) if resume is None else None
            yield from events
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
