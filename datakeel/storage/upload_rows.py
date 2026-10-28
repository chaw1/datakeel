# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resumable upload declarations and atomic publication receipts."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.core.models import new_id
from datakeel.storage.base import Base


class UploadRow(Base):
    """Persist a frozen upload declaration and its one successful dataset receipt."""

    __tablename__ = "uploads"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True)
    declaration: Mapped[dict[str, Any]] = mapped_column(JSON)
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("datasets.id"), nullable=True)
