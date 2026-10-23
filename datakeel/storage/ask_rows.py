# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Internal rows for immutable question sessions and fully replayable answers."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base


class AskSessionRow(Base):
    """Group local question turns with the actor who owns their audit context."""

    __tablename__ = "ask_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    actor: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)


class AskAnswerRow(Base):
    """Retain the exact request, question revision, SQL, parameters, and result."""

    __tablename__ = "ask_answers"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("ask_sessions.id"), index=True)
    producer_event_id: Mapped[str] = mapped_column(ForeignKey("lineage_events.event_id"))
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    question_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
