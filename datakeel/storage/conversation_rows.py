# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Durable conversation transcripts and idempotent user request ownership."""

from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base


class ConversationRow(Base):
    """Keep the complete conversation as one locked aggregate."""

    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    active_token: Mapped[str | None] = mapped_column(String, nullable=True)
    active_until: Mapped[float] = mapped_column(Float, default=0)
    canary: Mapped[str | None] = mapped_column(String, nullable=True)


class ConversationRequestRow(Base):
    """Replay a completed request without repeating controlled actions."""

    __tablename__ = "conversation_requests"
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String, primary_key=True)
    content: Mapped[str] = mapped_column(String)
    token: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class ConversationResumeRow(Base):
    """Own replayable recovery responses separately from user-message request keys."""

    __tablename__ = "conversation_resumes"
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String, primary_key=True)
    plan_id: Mapped[str] = mapped_column(String)
    token: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class ConversationAuditRow(Base):
    """Retain authorization denials and invalidations even after checkpoint deletion."""

    __tablename__ = "conversation_audit"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    plan_id: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    created_at: Mapped[float] = mapped_column(Float)
