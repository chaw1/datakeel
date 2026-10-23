# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Workflow facts are independent of conversation ownership and disposable checkpoints."""

from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base


class WorkflowRunRow(Base):
    """Freeze each explicit start and retain its public progress."""

    __tablename__ = "workflow_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String, index=True)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True)
    request_digest: Mapped[str] = mapped_column(String)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String)
    pending_plan_id: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)


class WorkflowStepRow(Base):
    """Persist outputs and status independently of graph replay."""

    __tablename__ = "workflow_steps"
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"), primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    output: Mapped[Any] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    plan_id: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class WorkflowAuditRow(Base):
    """Keep authorized and denied recovery evidence queryable after graph deletion."""

    __tablename__ = "workflow_audit"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    plan_id: Mapped[str | None] = mapped_column(String, nullable=True)
    kind: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    created_at: Mapped[float] = mapped_column(Float)


class WorkflowResumeRow(Base):
    """Bind each resume key to its original run and paused plan."""

    __tablename__ = "workflow_resumes"
    run_id: Mapped[str] = mapped_column(ForeignKey("workflow_runs.id"), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String, primary_key=True)
    plan_id: Mapped[str] = mapped_column(String)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
