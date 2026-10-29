# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Production fact tables with database-enforced exclusive assignment and append-only history."""

from pydantic import JsonValue
from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base
from datakeel.storage.pg_triggers import ensure_pg_trigger


class ProductionProjectRow(Base):
    """Persist project configuration separately from incrementally maintained task summaries."""

    __tablename__ = "production_projects"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class ProductionPackageRow(Base):
    """Keep stable package partition metadata without separately mutable workflow state."""

    __tablename__ = "production_packages"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("production_projects.id"), index=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class ProductionTaskRow(Base):
    """Index task selection, optimistic revision heads and rework ownership."""

    __tablename__ = "production_tasks"
    __table_args__ = (
        UniqueConstraint("project_id", "sample_id"),
        Index("production_task_next", "project_id", "state", "priority", "id"),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("production_projects.id"), index=True)
    package_id: Mapped[str] = mapped_column(ForeignKey("production_packages.id"), index=True)
    sample_id: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String, default="pending")
    round: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    latest_revision_id: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_revision_id: Mapped[str | None] = mapped_column(String, nullable=True)
    annotator_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class ProductionAssignmentRow(Base):
    """Enforce one effective assignment per task and stage in both supported databases."""

    __tablename__ = "production_assignments"
    __table_args__ = (
        Index(
            "production_unique_active_assignment",
            "task_id",
            "stage",
            unique=True,
            sqlite_where=text("active = 1"),
            postgresql_where=text("active = true"),
        ),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("production_tasks.id"), index=True)
    actor: Mapped[str] = mapped_column(String, index=True)
    stage: Mapped[str] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)
    # Enforced team-tier lease deadline (UTC epoch seconds); NULL when no lease is enforced.
    lease_expires_at: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)


class ProductionRevisionRow(Base):
    """Store only INSERT-able revision payloads and indexed provenance for exact statistics."""

    __tablename__ = "production_revisions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("production_tasks.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("production_projects.id"), index=True)
    source: Mapped[str] = mapped_column(String)
    actor: Mapped[str] = mapped_column(String)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class ProductionReviewRow(Base):
    """Keep each exact-revision review decision as immutable historical evidence."""

    __tablename__ = "production_reviews"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("production_tasks.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("production_projects.id"), index=True)
    annotator_id: Mapped[str] = mapped_column(String)
    decision: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class ProductionSummaryRow(Base):
    """Maintain exact counts transactionally for project and package state projections."""

    __tablename__ = "production_summaries"
    scope_id: Mapped[str] = mapped_column(String, primary_key=True)
    state: Mapped[str] = mapped_column(String, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class ProductionMemberRow(Base):
    """Remember distinct project participants for a one-time review suggestion."""

    __tablename__ = "production_members"
    project_id: Mapped[str] = mapped_column(ForeignKey("production_projects.id"), primary_key=True)
    actor: Mapped[str] = mapped_column(String, primary_key=True)


def install_production_constraints(connection: Connection, *, sqlite: bool) -> None:
    """Reject revision and review mutations even through direct SQL or alternate APIs."""
    if not sqlite:
        connection.execute(
            text("""
            CREATE OR REPLACE FUNCTION datakeel_immutable_production() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'production history is append-only'; END;
            $$ LANGUAGE plpgsql
        """)
        )
    for table in ("production_revisions", "production_reviews"):
        if sqlite:
            for operation in ("UPDATE", "DELETE"):
                connection.execute(
                    text(
                        f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} "
                        f"BEFORE {operation} ON {table} BEGIN "
                        "SELECT RAISE(ABORT, 'production history is append-only'); END"
                    )
                )
        else:
            # Current triggers need no table DDL, so startup never queues behind open writers.
            ensure_pg_trigger(
                connection,
                name=f"{table}_immutable",
                table=table,
                event="UPDATE OR DELETE",
                function="datakeel_immutable_production",
            )
