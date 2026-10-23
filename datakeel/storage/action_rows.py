# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist action plans, one-use approvals, execution runs, and their audit."""

from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.core.models import new_id, utcnow
from datakeel.storage.base import Base


class ActionPlanRow(Base):
    """Store the canonical frozen plan independently of its execution status."""

    __tablename__ = "action_plans"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    action_type: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="PREPARED")
    created_at: Mapped[float] = mapped_column(Float, default=lambda: utcnow().timestamp())


class ApprovalRow(Base):
    """Bind a single human decision to a plan digest and consumption state."""

    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(ForeignKey("action_plans.id"), unique=True)
    plan_digest: Mapped[str] = mapped_column(String)
    actor: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[float] = mapped_column(Float, default=lambda: utcnow().timestamp())


class ActionRunRow(Base):
    """Keep each attempted execution and its optional asynchronous task."""

    __tablename__ = "action_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(ForeignKey("action_plans.id"), index=True)
    action_type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    task_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    receipt: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=lambda: utcnow().timestamp())
    completed_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class ActionAuditRow(Base):
    """Record attributed policy decisions and execution outcomes atomically."""

    __tablename__ = "action_audit"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(ForeignKey("action_plans.id"), index=True)
    action_type: Mapped[str] = mapped_column(String)
    phase: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    actor: Mapped[str] = mapped_column(String)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[float] = mapped_column(Float, default=lambda: utcnow().timestamp())


class ActionOperationRow(Base):
    """Bind one caller operation to an immutable request and its original run."""

    __tablename__ = "action_operations"
    operation_id: Mapped[str] = mapped_column(String, primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("action_plans.id"))
    actor: Mapped[str] = mapped_column(String)
    request_digest: Mapped[str] = mapped_column(String)
    run_id: Mapped[str] = mapped_column(ForeignKey("action_runs.id"), unique=True)
