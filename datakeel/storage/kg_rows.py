# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Disposable block caches and durable execution metadata, separate from graph facts."""

from typing import Any

from sqlalchemy import JSON, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.core.models import utcnow
from datakeel.storage.base import Base


class KGRunRow(Base):
    """Keep frozen worker inputs and progress without duplicating assertion facts."""

    __tablename__ = "kg_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String, index=True)
    version_id: Mapped[str] = mapped_column(String, index=True)
    task_id: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class KGCacheRow(Base):
    """Cache only complete raw block output under its full semantic input digest."""

    __tablename__ = "kg_block_cache"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    key_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, default=lambda: utcnow().timestamp())
