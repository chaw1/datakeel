# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Durable documentation snapshots with a separately controlled publication state."""

from pydantic import JsonValue
from sqlalchemy import JSON, Boolean, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base


class DatasheetRow(Base):
    """Retain immutable checked facts and prose for one explicit dataset version."""

    __tablename__ = "datasheets"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("versions.id"), index=True)
    created_at: Mapped[float] = mapped_column(Float, index=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
