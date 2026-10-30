# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Durable one-sentence action chains; every step's authority stays in its action plans."""

from pydantic import JsonValue
from sqlalchemy import JSON, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base


class ActionChainRow(Base):
    """Keep the ordered steps, their plan identities and progress for resuming."""

    __tablename__ = "action_chains"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String, index=True)
    updated_at: Mapped[float] = mapped_column(Float)
    lease_until: Mapped[float] = mapped_column(Float, default=0.0)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)
