# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Internal persistence mapping for durable tool invocation spans."""

from sqlalchemy import JSON, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.core.models import new_id, utcnow
from datakeel.storage.base import Base


class ToolInvocationRow(Base):
    """Keep one durable start and completion record per invocation identity."""

    __tablename__ = "tool_invocation"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String, index=True)
    actor: Mapped[str] = mapped_column(String)
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    parameters_summary: Mapped[dict[str, object]] = mapped_column(JSON)
    asset_refs: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="RUNNING")
    started_at: Mapped[float] = mapped_column(Float, default=lambda: utcnow().timestamp())
    completed_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    elapsed_ms: Mapped[float] = mapped_column(Float, default=0)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
