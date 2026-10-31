# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Relational catalog identities and immutable published label vocabulary versions."""

from pydantic import JsonValue
from sqlalchemy import JSON, Boolean, Integer, String, UniqueConstraint, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base
from datakeel.storage.pg_triggers import ensure_pg_trigger


class ProductionLabelSetRow(Base):
    """Keep drafts editable and published versions sealed by database constraints."""

    __tablename__ = "production_label_sets"
    __table_args__ = (UniqueConstraint("label_set_id", "version"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    label_set_id: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[int] = mapped_column(Integer)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class ProductionTemplateRow(Base):
    """Store reusable template definitions with optimistic revisions and soft deletion."""

    __tablename__ = "production_templates"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class ProductionTemplateVersionRow(Base):
    """Keep every saved template revision so each project reads the exact version it locked."""

    __tablename__ = "production_template_versions"
    __table_args__ = (UniqueConstraint("template_id", "revision"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    template_id: Mapped[str] = mapped_column(String, index=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class ProductionModelRow(Base):
    """Store approved model configurations independently of historic model provenance."""

    __tablename__ = "production_models"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class ProductionPrelabelRunRow(Base):
    """Keep model import and offline run attribution as append-only facts."""

    __tablename__ = "production_prelabel_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


def install_catalog_constraints(connection: Connection, *, sqlite: bool) -> None:
    """Reject updates and deletes of published vocabularies and saved template versions."""
    if sqlite:
        for operation in ("UPDATE", "DELETE"):
            connection.execute(
                text(
                    f"CREATE TRIGGER IF NOT EXISTS production_labels_no_{operation.lower()} "
                    f"BEFORE {operation} ON production_label_sets WHEN OLD.published = 1 BEGIN "
                    "SELECT RAISE(ABORT, 'published label sets are immutable'); END"
                )
            )
            connection.execute(
                text(
                    f"CREATE TRIGGER IF NOT EXISTS production_template_versions_no_"
                    f"{operation.lower()} BEFORE {operation} ON production_template_versions "
                    "BEGIN SELECT RAISE(ABORT, 'template versions are immutable'); END"
                )
            )
        return
    connection.execute(
        text("""
        CREATE OR REPLACE FUNCTION datakeel_immutable_label_set() RETURNS trigger AS $$
        BEGIN IF OLD.published THEN
            RAISE EXCEPTION 'published label sets are immutable';
        END IF; IF TG_OP = 'DELETE' THEN RETURN OLD; END IF; RETURN NEW; END;
        $$ LANGUAGE plpgsql
        """)
    )
    ensure_pg_trigger(
        connection,
        name="datakeel_label_set_immutable",
        table="production_label_sets",
        event="UPDATE OR DELETE",
        function="datakeel_immutable_label_set",
    )
    connection.execute(
        text("""
        CREATE OR REPLACE FUNCTION datakeel_immutable_template_version() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'template versions are immutable'; END;
        $$ LANGUAGE plpgsql
        """)
    )
    ensure_pg_trigger(
        connection,
        name="datakeel_template_version_immutable",
        table="production_template_versions",
        event="UPDATE OR DELETE",
        function="datakeel_immutable_template_version",
    )
