# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Private custom-operator source versions and append-only execution records."""

from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base


class CustomOperatorRow(Base):
    """Store one immutable approved name and content-hash version."""

    __tablename__ = "custom_operator_versions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, index=True)
    code_hash: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class CustomRunRow(Base):
    """Retain audit facts for each isolated attempt without storing user output bytes."""

    __tablename__ = "custom_operator_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    code_hash: Mapped[str] = mapped_column(String, index=True)
    task_id: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
