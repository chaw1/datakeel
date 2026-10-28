# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist release reconciliation receipts without changing immutable release facts."""

from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base


class ReconciliationRow(Base):
    """Archive one complete six-category verification for a published release."""

    __tablename__ = "release_reconciliations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    release_id: Mapped[str] = mapped_column(ForeignKey("releases.id"), index=True)
    created_at: Mapped[float] = mapped_column(Float)
    report: Mapped[dict[str, Any]] = mapped_column(JSON)
