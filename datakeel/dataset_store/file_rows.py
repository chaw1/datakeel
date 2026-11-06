# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Private overlay, discovery and upload rows owned by the dataset store."""

from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.core.models import new_id
from datakeel.core.schema import Base


class FileStateRow(Base):
    """Persist logical quarantine/deletion state shared by all file versions."""

    __tablename__ = "file_states"
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), primary_key=True)
    file_id: Mapped[str] = mapped_column(String, primary_key=True)
    quarantined: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=0)


_IDENTITY = String().with_variant(String(collation="C"), "postgresql")


class FileDiscoveryRow(Base):
    """Store public navigation per immutable version, never mutable file state."""

    __tablename__ = "file_discovery"
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    file_id: Mapped[str] = mapped_column(_IDENTITY)
    name: Mapped[str] = mapped_column(String)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE", onupdate="CASCADE"), index=True
    )
    version_id: Mapped[str] = mapped_column(
        _IDENTITY,
        ForeignKey("versions.id", ondelete="CASCADE", onupdate="CASCADE"),
        index=True,
    )
    created_at: Mapped[float] = mapped_column(Float)


class FileDiscoveryCheckpointRow(Base):
    """Record completed migrations and a sticky need for exact Python JSON reads."""

    __tablename__ = "file_discovery_checkpoints"
    generation: Mapped[str] = mapped_column(String, primary_key=True)


class UploadRow(Base):
    """Persist a frozen upload declaration and its one successful dataset receipt."""

    __tablename__ = "uploads"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True)
    declaration: Mapped[dict[str, Any]] = mapped_column(JSON)
    dataset_id: Mapped[str | None] = mapped_column(ForeignKey("datasets.id"), nullable=True)
