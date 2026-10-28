# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Append-only published release headers and individually indexed manifest entries."""

from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base


class ReleaseRow(Base):
    """Persist one frozen publication independently of mutable dataset settings."""

    __tablename__ = "releases"
    __table_args__ = (UniqueConstraint("dataset_id", "tag"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("versions.id"), index=True)
    tag: Mapped[str] = mapped_column(String)
    notes: Mapped[str] = mapped_column(String)
    created_at: Mapped[float] = mapped_column(Float)
    manifest_sha256: Mapped[str] = mapped_column(String)
    file_count: Mapped[int] = mapped_column(Integer)
    total_bytes: Mapped[int] = mapped_column(Integer)
    metadata_values: Mapped[dict[str, Any]] = mapped_column(JSON)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON)


class ReleaseEntryRow(Base):
    """Keep portable frozen facts separate from private object resolution keys."""

    __tablename__ = "release_entries"
    __table_args__ = (UniqueConstraint("release_id", "ordinal"),)
    release_id: Mapped[str] = mapped_column(
        ForeignKey("releases.id", deferrable=True, initially="DEFERRED"), primary_key=True
    )
    file_id: Mapped[str] = mapped_column(String, primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    object_key: Mapped[str] = mapped_column(String)
    record: Mapped[dict[str, Any]] = mapped_column(JSON)
