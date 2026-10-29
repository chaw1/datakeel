# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Internal persistence for metric question threads and their latest query frame."""

from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base


class AskConversationRow(Base):
    """Keep question conversation state apart from Agent runtime state."""

    __tablename__ = "ask_conversations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    actor: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String, index=True)
    answer_ids: Mapped[list[str]] = mapped_column(JSON)
    frame_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
