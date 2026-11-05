# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persistent fake-only accounts, attempts and disposable two-level projections."""

from typing import Any

from sqlalchemy import JSON, BigInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.core.models import new_id
from datakeel.storage.base import Base


class VectorAccountRow(Base):
    """Serialize request and cost occupancy independently from real model budgets."""

    __tablename__ = "vector_fake_accounts"
    plan_id: Mapped[str] = mapped_column(String, primary_key=True)
    requests: Mapped[int] = mapped_column(BigInteger, default=0)
    cost_nanos: Mapped[int] = mapped_column(BigInteger, default=0)


class VectorAttemptRow(Base):
    """Persist one nonretryable call identity before any fake dispatch occurs."""

    __tablename__ = "vector_fake_attempts"
    __table_args__ = (UniqueConstraint("task_id", "node_id", "asset_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(String, index=True)
    task_id: Mapped[str] = mapped_column(String, index=True)
    node_id: Mapped[str] = mapped_column(String)
    asset_id: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String, default="RESERVED")
    token_bound: Mapped[int] = mapped_column(BigInteger)
    reserved_nanos: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class VectorCacheRow(Base):
    """Keep fake, recording and real namespaces structurally separate."""

    __tablename__ = "vector_cache"
    namespace_key: Mapped[str] = mapped_column(String, primary_key=True)
    producer_event_id: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


VECTOR_MODELS = (VectorAccountRow, VectorAttemptRow, VectorCacheRow)
