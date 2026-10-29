# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bind runtime sessions to server-selected actors without changing legacy view schemas."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.core.errors import AuthorizationError
from datakeel.storage.base import Base

if TYPE_CHECKING:
    from datakeel.storage.database import Database


class IdentitySessionRow(Base):
    """Store the authoritative owner of an Agent conversation or deterministic workflow."""

    __tablename__ = "identity_sessions"
    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    actor: Mapped[str] = mapped_column(String)


REGISTERED_IDENTITY_RUNTIME_ROWS = (IdentitySessionRow,)


def session_actor(db: Database, session_id: str) -> str:
    """Read the authoritative actor, retaining local ownership for legacy sessions."""
    with db.session() as session:
        row = session.get(IdentitySessionRow, session_id)
        return row.actor if row is not None else "local"


def bind_session_actor(db: Database, session_id: str, actor: str) -> None:
    """Bind a newly created session once; a later request cannot replace its owner."""
    with db.session() as session:
        db.lock_writes(session)
        row = session.get(IdentitySessionRow, session_id, with_for_update=True)
        if row is not None and row.actor != actor:
            msg = "Runtime session belongs to another actor"
            raise AuthorizationError(msg)
        if row is None:
            session.add(IdentitySessionRow(session_id=session_id, actor=actor))
        session.commit()


def require_session_actor(db: Database, session_id: str, actor: str) -> None:
    """Prevent a request from borrowing a more privileged conversation or workflow."""
    if session_actor(db, session_id) != actor:
        msg = "Runtime session belongs to another actor"
        raise AuthorizationError(msg)
