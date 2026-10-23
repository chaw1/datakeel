# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Public conversation creation, replay, and controlled response streaming."""

from collections.abc import Iterator

from datakeel.agent.factory import provider_session
from datakeel.agent.memory import close_interrupted, conversation_view
from datakeel.agent.models import AgentEvent, ConversationView
from datakeel.core.agent_models import ConversationCreate, MessageInput, Provider
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument
from datakeel.runtime.graph import AgentGraph
from datakeel.storage import conversation_store as memory
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import get_dataset


def create_conversation(db: Database, request: ConversationCreate) -> ConversationView:
    """Validate an optional workspace and persist the new session configuration."""
    if request.dataset_id is not None:
        get_dataset(db, request.dataset_id)
    return conversation_view(db, memory.create(db, request))


def get_conversation(db: Database, conversation_id: str) -> ConversationView:
    """Read all messages and hydrate plan cards with the latest human decisions."""
    return conversation_view(db, memory.get(db, conversation_id))


def list_conversations(db: Database) -> list[ConversationView]:
    """List persisted local conversations with complete transcript views."""
    return [conversation_view(db, item) for item in memory.list_all(db)]


def send_message(
    db: Database,
    conversation_id: str,
    request: MessageInput,
    *,
    provider: Provider | None = None,
) -> Iterator[AgentEvent]:
    """Stream durable events; replay a completed request without executing it again."""
    lease = memory.begin(db, conversation_id, request)
    if lease.replay is not None:
        yield from (AgentEvent.model_validate(document.root) for document in lease.replay)
        return
    completed = False
    try:
        for event in _response_events(db, conversation_id, lease.token, provider):
            memory.append(
                db,
                conversation_id,
                lease.token,
                event=JsonDocument.model_validate(event.model_dump(mode="json")),
            )
            yield event
        done = AgentEvent(event="done")
        memory.append(
            db,
            conversation_id,
            lease.token,
            event=JsonDocument.model_validate(done.model_dump(mode="json")),
        )
        completed = True
        yield done
    finally:
        if not completed:
            close_interrupted(db, conversation_id, lease.token)
        memory.finish(db, conversation_id, lease.token, completed=completed)


def _response_events(
    db: Database, conversation_id: str, token: str, provider: Provider | None
) -> Iterator[AgentEvent]:
    config = memory.get(db, conversation_id).config
    try:
        with provider_session(config, provider) as selected:
            yield from AgentGraph(db, conversation_id, token, selected).run()
    except ValidationError as error:
        yield AgentEvent(event="stopped", stop_reason="configuration_error", text=str(error))
