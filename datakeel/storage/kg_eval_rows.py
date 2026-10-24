# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Append-only knowledge-graph evaluation rows in the shared metadata collection."""

from pydantic import JsonValue
from sqlalchemy import JSON, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base


class KGEvalRunRow(Base):
    """Separate graph report payloads from established conversation evaluation schemas."""

    __tablename__ = "kg_eval_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    profile: Mapped[str] = mapped_column(String, index=True)
    model: Mapped[str] = mapped_column(String, index=True)
    suite_digest: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, index=True)
