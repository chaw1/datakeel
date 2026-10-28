# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Durable quality rule revisions, execution results, incidents and alert outbox."""

from pydantic import JsonValue
from sqlalchemy import JSON, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base


class DqRuleRow(Base):
    """Keep the current rule and a tombstone after deletion."""

    __tablename__ = "dq_rules"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer)
    deleted: Mapped[bool] = mapped_column(default=False)
    source_id: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class DqHistoryRow(Base):
    """Retain immutable accepted rule mutations and human issue decisions."""

    __tablename__ = "dq_history"
    __table_args__ = (UniqueConstraint("rule_id", "revision"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    rule_id: Mapped[str] = mapped_column(String, index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class DqRunRow(Base):
    """Bind each rule revision and minute or manual key to a single task."""

    __tablename__ = "dq_runs"
    __table_args__ = (UniqueConstraint("rule_id", "rule_revision", "slot"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    rule_id: Mapped[str] = mapped_column(String, index=True)
    rule_revision: Mapped[int] = mapped_column(Integer)
    slot: Mapped[str] = mapped_column(String)
    task_id: Mapped[str] = mapped_column(String, unique=True)
    state: Mapped[str] = mapped_column(String, default="QUEUED")
    rule_payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)
    result_id: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)


class DqResultRow(Base):
    """Keep every fenced execution result, independently of later rule changes."""

    __tablename__ = "dq_results"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, unique=True)
    rule_id: Mapped[str] = mapped_column(String, index=True)
    rule_revision: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[float] = mapped_column(Float, index=True)
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class DqIssueRow(Base):
    """Store the latest incident state while preserving all decisions separately."""

    __tablename__ = "dq_issues"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    rule_id: Mapped[str] = mapped_column(String, index=True)
    active: Mapped[bool] = mapped_column(default=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class DqIssueAuditRow(Base):
    """Append an actor-attributed record for automatic and human transitions."""

    __tablename__ = "dq_issue_audits"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    issue_id: Mapped[str] = mapped_column(String, index=True)
    actor: Mapped[str] = mapped_column(String)
    occurred_at: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class DqWebhookRow(Base):
    """Persist retries with expiring delivery leases and an immutable event body."""

    __tablename__ = "dq_webhook_outbox"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    body: Mapped[str] = mapped_column(String)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[float] = mapped_column(Float, index=True)
    delivered: Mapped[bool] = mapped_column(default=False)
    lease_owner: Mapped[str | None] = mapped_column(String, nullable=True)
    leased_until: Mapped[float | None] = mapped_column(Float, nullable=True)
