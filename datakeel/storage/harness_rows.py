# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Internal append-only model-call and deterministic evaluation records."""

from typing import Any

from sqlalchemy import JSON, BigInteger, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.core.models import new_id, utcnow
from datakeel.storage.base import Base


class ModelCallTraceRow(Base):
    """Persist one complete trace for each settled provider reservation."""

    __tablename__ = "model_call_trace"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    reservation_id: Mapped[str] = mapped_column(String, unique=True)
    conversation_id: Mapped[str] = mapped_column(String, index=True)
    accounting_conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_path: Mapped[str | None] = mapped_column(String, nullable=True)
    depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_tool_call_id: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str] = mapped_column(String, index=True)
    day: Mapped[str] = mapped_column(String, index=True)
    cost_nanos: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, default=lambda: utcnow().timestamp())


class EvalRunRow(Base):
    """Keep each evaluation report for explicit comparison with its predecessor."""

    __tablename__ = "eval_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String, index=True)
    suite_digest: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, default=lambda: utcnow().timestamp())
