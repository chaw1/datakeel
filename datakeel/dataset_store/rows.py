# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Internal rows owned by this store; no business behavior."""

from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.core.models import new_id, utcnow
from datakeel.core.schema import Base
from datakeel.dataset_store.file_rows import (
    FileDiscoveryCheckpointRow,
    FileDiscoveryRow,
    FileStateRow,
    UploadRow,
)

__all__ = [
    "DatasetRow",
    "EventRow",
    "FileDiscoveryCheckpointRow",
    "FileDiscoveryRow",
    "FileStateRow",
    "MetadataChangeRow",
    "UploadRow",
    "VersionRow",
]


class DatasetRow(Base):
    """Internal persistence record for dataset facts."""

    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[float] = mapped_column(Float, default=lambda: utcnow().timestamp())
    files: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    quality_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    template: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    metadata_values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    compliance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class VersionRow(Base):
    """Internal persistence record for version facts."""

    __tablename__ = "versions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    created_at: Mapped[float] = mapped_column(Float, default=lambda: utcnow().timestamp())
    manifest: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    task_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)


class EventRow(Base):
    """Internal persistence record for event facts."""

    __tablename__ = "lineage_events"
    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class MetadataChangeRow(Base):
    """Internal persistence record for metadatachange facts."""

    __tablename__ = "metadata_changes"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    field: Mapped[str] = mapped_column(String)
    before: Mapped[Any] = mapped_column(JSON, nullable=True)
    after: Mapped[Any] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    occurred_at: Mapped[float] = mapped_column(Float, default=lambda: utcnow().timestamp())
