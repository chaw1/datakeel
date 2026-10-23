# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent recovery request leases with exact event replay and no new user messages."""

from datetime import timedelta

from datakeel.core.agent_models import ConversationLease, ResumeInput
from datakeel.core.errors import ConflictError
from datakeel.core.models import JsonDocument, new_id, utcnow
from datakeel.storage.conversation_rows import ConversationResumeRow
from datakeel.storage.conversation_store import locked_conversation
from datakeel.storage.database import Database


def abandoned_token(db: Database, conversation_id: str) -> str | None:
    """Read a stale lease only after the caller acquired the process-released response lock."""
    with db.session() as session:
        return locked_conversation(session, conversation_id).active_token


def begin_resume(db: Database, conversation_id: str, request: ResumeInput) -> ConversationLease:
    """Claim a recovery response, allowing interrupted recovery requests to continue safely."""
    with db.session() as session:
        db.lock_writes(session)
        row = locked_conversation(session, conversation_id)
        previous = session.get(ConversationResumeRow, (conversation_id, request.idempotency_key))
        if previous is not None:
            if previous.plan_id != request.plan_id:
                msg = "Idempotency key is bound to a different resume plan"
                raise ConflictError(msg)
            if previous.status == "COMPLETED":
                return ConversationLease(
                    token=previous.token, replay=[JsonDocument(item) for item in previous.events]
                )
        if row.active_token and row.active_until > utcnow().timestamp():
            msg = "Conversation already has an active response"
            raise ConflictError(msg)
        token = new_id()
        row.active_token = token
        row.active_until = (utcnow() + timedelta(hours=1)).timestamp()
        if previous is None:
            previous = ConversationResumeRow(
                conversation_id=conversation_id,
                key=request.idempotency_key,
                plan_id=request.plan_id,
            )
            session.add(previous)
        previous.token, previous.status, previous.events = token, "RUNNING", []
        session.commit()
        return ConversationLease(token=token)
