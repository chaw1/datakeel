# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Internal queue-job state for optional paragraph generation."""

from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.core.models import utcnow
from datakeel.storage.base import Base


class DatasheetJobRow(Base):
    """Persist the approved input snapshot separately from public task progress."""

    __tablename__ = "datasheet_jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    prepared: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="QUEUED")
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=lambda: utcnow().timestamp())
