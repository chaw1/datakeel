# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Internal rows owned by this store; no business behavior."""

from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.core.models import new_id, utcnow
from datakeel.core.schema import Base


class TaskRow(Base):
    """Internal persistence record for task facts."""

    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True)
    state: Mapped[str] = mapped_column(String, default="QUEUED")
    queue: Mapped[str] = mapped_column(String, default="cpu")
    pipeline: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=lambda: utcnow().timestamp())
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_shards: Mapped[int] = mapped_column(Integer, default=1)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    input_version_id: Mapped[str | None] = mapped_column(String, nullable=True)
    kg_run_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    dq_run_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    datasheet_job_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)


class ShardRow(Base):
    """Internal persistence record for shard facts."""

    __tablename__ = "task_shards"
    __table_args__ = (UniqueConstraint("task_id", "ordinal"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String, default="QUEUED", index=True)
    inputs: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    outputs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    lease_owner: Mapped[str | None] = mapped_column(String, nullable=True)
    heartbeat_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    lease_expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class OutboxRow(Base):
    """Internal persistence record for outbox facts."""

    __tablename__ = "outbox"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    delivered: Mapped[bool] = mapped_column(default=False, index=True)
