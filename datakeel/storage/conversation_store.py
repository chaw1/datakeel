# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Transactional session memory that never drops earlier messages or results."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.agent_models import (
    ChatMessage,
    Conversation,
    ConversationCreate,
    ConversationLease,
    MessageInput,
)
from datakeel.core.errors import ConflictError, NotFoundError
from datakeel.core.models import JsonDocument, new_id, utcnow
from datakeel.storage.conversation_rows import ConversationRequestRow, ConversationRow
from datakeel.storage.database import Database


def create(db: Database, config: ConversationCreate) -> Conversation:
    """Persist one local conversation before any model or tool invocation."""
    view = Conversation(id=new_id(), config=config)
    with db.session() as session:
        session.add(ConversationRow(id=view.id, payload=view.model_dump(mode="json")))
        session.commit()
    return view


def get(db: Database, conversation_id: str) -> Conversation:
    """Read all durable messages and events in original order."""
    with db.session() as session:
        return Conversation.model_validate(_row(session, conversation_id).payload)


def list_all(db: Database) -> list[Conversation]:
    """List complete local sessions in deterministic creation order."""
    with db.session() as session:
        rows = session.scalars(select(ConversationRow)).all()
        return sorted(
            (Conversation.model_validate(row.payload) for row in rows),
            key=lambda item: item.created_at,
        )


def begin(db: Database, conversation_id: str, request: MessageInput) -> ConversationLease:
    """Claim one user turn or replay its already completed events."""
    with db.session() as session:
        db.lock_writes(session)
        row = _row(session, conversation_id)
        previous = session.get(ConversationRequestRow, (conversation_id, request.idempotency_key))
        if previous is not None:
            if previous.content != request.content:
                msg = "Idempotency key is bound to a different user message"
                raise ConflictError(msg)
            if previous.status == "COMPLETED":
                return ConversationLease(
                    token=previous.token, replay=[JsonDocument(item) for item in previous.events]
                )
            msg = "User message is already in progress or was interrupted"
            raise ConflictError(msg)
        if row.active_token and row.active_until > utcnow().timestamp():
            msg = "Conversation already has an active response"
            raise ConflictError(msg)
        token = new_id()
        row.active_token = token
        row.active_until = (utcnow() + timedelta(hours=1)).timestamp()
        view = Conversation.model_validate(row.payload)
        row.payload = view.model_copy(
            update={"messages": [*view.messages, ChatMessage(role="user", content=request.content)]}
        ).model_dump(mode="json")
        session.add(
            ConversationRequestRow(
                conversation_id=conversation_id,
                key=request.idempotency_key,
                content=request.content,
                token=token,
                status="RUNNING",
                events=[],
            )
        )
        session.commit()
    return ConversationLease(token=token)


def append(
    db: Database,
    conversation_id: str,
    token: str,
    *,
    message: ChatMessage | None = None,
    event: JsonDocument | None = None,
    model_call: bool = False,
) -> Conversation:
    """Append a complete exchange under the current response lease."""
    with db.session() as session:
        db.lock_writes(session)
        row = _owned(session, conversation_id, token)
        view = Conversation.model_validate(row.payload)
        updated = view.model_copy(
            update={
                "messages": [*view.messages, message] if message else view.messages,
                "events": [*view.events, event] if event else view.events,
                "turns": view.turns + int(model_call),
            }
        )
        row.payload = updated.model_dump(mode="json")
        if event is not None:
            request = session.scalar(
                select(ConversationRequestRow).where(ConversationRequestRow.token == token)
            )
            if request is None:
                msg = "Conversation request disappeared"
                raise ConflictError(msg)
            request.events = [*request.events, event.model_dump(mode="json")]
        session.commit()
    return updated


def finish(db: Database, conversation_id: str, token: str, *, completed: bool) -> None:
    """Release response ownership while retaining its replay or interruption record."""
    with db.session() as session:
        db.lock_writes(session)
        row = _owned(session, conversation_id, token)
        request = session.scalar(
            select(ConversationRequestRow).where(ConversationRequestRow.token == token)
        )
        if request is not None:
            request.status = "COMPLETED" if completed else "INTERRUPTED"
        row.active_token = None
        session.commit()


def _row(session: Session, conversation_id: str) -> ConversationRow:
    row = session.scalar(
        select(ConversationRow).where(ConversationRow.id == conversation_id).with_for_update()
    )
    if row is None:
        msg = "Conversation not found"
        raise NotFoundError(msg)
    return row


def _owned(session: Session, conversation_id: str, token: str) -> ConversationRow:
    row = _row(session, conversation_id)
    if row.active_token != token:
        msg = "Conversation response ownership changed"
        raise ConflictError(msg)
    return row
