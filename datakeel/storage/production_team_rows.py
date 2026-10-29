# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Append-only team lease releases and package inspection decisions."""

from pydantic import JsonValue
from sqlalchemy import JSON, Float, ForeignKey, String, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base
from datakeel.storage.pg_triggers import ensure_pg_trigger

TEAM_HISTORY_TABLES = ("production_lease_releases", "production_package_inspections")


class ProductionLeaseReleaseRow(Base):
    """Key each release by assignment so the database admits at most one per assignment."""

    __tablename__ = "production_lease_releases"
    assignment_id: Mapped[str] = mapped_column(
        ForeignKey("production_assignments.id"), primary_key=True
    )
    task_id: Mapped[str] = mapped_column(ForeignKey("production_tasks.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("production_projects.id"), index=True)
    actor: Mapped[str] = mapped_column(String, index=True)
    reason: Mapped[str] = mapped_column(String)
    released_at: Mapped[float] = mapped_column(Float, index=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class ProductionPackageInspectionRow(Base):
    """Keep every signed package acceptance or rejection as immutable evidence."""

    __tablename__ = "production_package_inspections"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    package_id: Mapped[str] = mapped_column(ForeignKey("production_packages.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("production_projects.id"), index=True)
    created_at: Mapped[float] = mapped_column(Float, index=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


def install_team_constraints(connection: Connection, *, sqlite: bool) -> None:
    """Reject UPDATE and DELETE of release and inspection history in both databases."""
    for table in TEAM_HISTORY_TABLES:
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
            # The shared immutable-history function is created by the production constraints.
            ensure_pg_trigger(
                connection,
                name=f"{table}_immutable",
                table=table,
                event="UPDATE OR DELETE",
                function="datakeel_immutable_production",
            )
