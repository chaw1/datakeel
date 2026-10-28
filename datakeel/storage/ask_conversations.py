# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Actor-owned persistent question conversations with bounded retention."""

from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from datakeel.core.ask_conversation_models import AskConversation
from datakeel.core.ask_frame_models import AskQueryFrame
from datakeel.core.ask_models import AskAnswer, AskRequest
from datakeel.core.errors import ConflictError, NotFoundError
from datakeel.core.models import new_id, utcnow
from datakeel.core.settings import get_settings
from datakeel.storage.ask_conversation_rows import AskConversationRow
from datakeel.storage.ask_rows import AskAnswerRow, AskSessionRow
from datakeel.storage.ask_store import answer_in_session, store_answer_in_session
from datakeel.storage.database import Database


def _owned(session: Session, conversation_id: str, actor: str) -> AskConversationRow:
    row = session.scalar(
        select(AskConversationRow).where(AskConversationRow.id == conversation_id).with_for_update()
    )
    if row is None or row.actor != actor:
        msg = f"Question conversation not found: {conversation_id}"
        raise NotFoundError(msg)
    return row


def _view(session: Session, row: AskConversationRow) -> AskConversation:
    return AskConversation(
        id=row.id,
        actor=row.actor,
        title=row.title,
        created_at=datetime.fromisoformat(row.created_at),
        updated_at=datetime.fromisoformat(row.updated_at),
        current_frame=None
        if row.frame_payload is None
        else AskQueryFrame.model_validate(row.frame_payload),
        turns=tuple(answer_in_session(session, identity) for identity in row.answer_ids),
    )


def _remove(session: Session, row: AskConversationRow) -> None:
    answers = list(session.scalars(select(AskAnswerRow).where(AskAnswerRow.id.in_(row.answer_ids))))
    session_ids = {answer.session_id for answer in answers}
    for answer in answers:
        session.delete(answer)
    session.delete(row)
    session.flush()
    for identity in session_ids:
        remaining = session.scalar(
            select(AskAnswerRow.id).where(AskAnswerRow.session_id == identity)
        )
        if remaining is None:
            session.execute(delete(AskSessionRow).where(AskSessionRow.id == identity))


def _expire(session: Session) -> None:
    cutoff = (utcnow() - timedelta(days=get_settings().ask_conversation_retention_days)).isoformat()
    for row in session.scalars(
        select(AskConversationRow).where(AskConversationRow.updated_at < cutoff)
    ):
        _remove(session, row)


def create_conversation(
    db: Database, actor: str = "local-user", title: str = "新问数会话"
) -> AskConversation:
    """Create an empty independently addressable question conversation."""
    with db.session() as session:
        db.lock_writes(session)
        _expire(session)
        now = utcnow().isoformat()
        row = AskConversationRow(
            id=new_id(), actor=actor, title=title, created_at=now, updated_at=now, answer_ids=[]
        )
        session.add(row)
        session.flush()
        result = _view(session, row)
        session.commit()
        return result


def list_conversations(db: Database, actor: str = "local-user") -> tuple[AskConversation, ...]:
    """List only the caller's unexpired question threads, newest first."""
    with db.session() as session:
        db.lock_writes(session)
        _expire(session)
        rows = session.scalars(
            select(AskConversationRow)
            .where(AskConversationRow.actor == actor)
            .order_by(AskConversationRow.updated_at.desc(), AskConversationRow.id)
        )
        result = tuple(_view(session, row) for row in rows)
        session.commit()
        return result


def get_conversation(
    db: Database, conversation_id: str, actor: str = "local-user"
) -> AskConversation:
    """Restore an owned question thread from persistent answer evidence."""
    with db.session() as session:
        db.lock_writes(session)
        _expire(session)
        result = _view(session, _owned(session, conversation_id, actor))
        session.commit()
        return result


def delete_conversation(db: Database, conversation_id: str, actor: str = "local-user") -> None:
    """Delete the thread, saved frames and answer replay rows; retain immutable audit facts."""
    with db.session() as session:
        db.lock_writes(session)
        _remove(session, _owned(session, conversation_id, actor))
        session.commit()


def store_conversation_turn(
    db: Database,
    request: AskRequest,
    answer: AskAnswer,
    previous: AskConversation | None,
) -> AskAnswer:
    """Commit the answer evidence and optimistic thread update in one transaction."""
    with db.session() as session:
        db.lock_writes(session)
        _expire(session)
        row = (
            _owned(session, previous.id, request.actor)
            if previous is not None
            else session.get(AskConversationRow, answer.conversation_id)
        )
        if (
            row is not None
            and previous is not None
            and row.updated_at != previous.updated_at.isoformat()
        ):
            msg = "Question conversation changed while this turn was executing; retry the turn"
            raise ConflictError(msg)
        if row is None:
            now = utcnow().isoformat()
            row = AskConversationRow(
                id=answer.conversation_id,
                actor=request.actor,
                title=request.question[:120],
                created_at=now,
                updated_at=now,
                answer_ids=[],
            )
            session.add(row)
        stored = store_answer_in_session(session, request, answer)
        row.answer_ids = [*row.answer_ids, stored.id]
        row.updated_at = utcnow().isoformat()
        frame = stored.query_frame
        row.frame_payload = None if frame is None else frame.model_dump(mode="json")
        session.commit()
        return stored
