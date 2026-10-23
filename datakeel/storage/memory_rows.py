# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Memory facts, content-free write replay keys and deletion audits."""

from typing import Any

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base


class MemoryRow(Base):
    """Store active and archived typed memory payloads in the authoritative database."""

    __tablename__ = "memories"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class MemoryWriteRow(Base):
    """Prevent a retried write from resurrecting a subsequently deleted memory."""

    __tablename__ = "memory_writes"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    digest: Mapped[str] = mapped_column(String)
    memory_id: Mapped[str] = mapped_column(String)


class MemoryUseRow(Base):
    """Deduplicate reinforcement by root user question, retaining only identities."""

    __tablename__ = "memory_uses"
    root_conversation_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_message_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    memory_id: Mapped[str] = mapped_column(String, primary_key=True)


class MemoryAuditRow(Base):
    """Retain only identities and timestamps after hard deletion."""

    __tablename__ = "memory_audit"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
