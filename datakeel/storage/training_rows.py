# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable version-owned named training partitions."""

from pydantic import JsonValue
from sqlalchemy import JSON, Float, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base
from datakeel.storage.pg_triggers import ensure_pg_trigger


class TrainingSplitRow(Base):
    """Retain assignment and annotation snapshots behind a unique version-scoped name."""

    __tablename__ = "training_splits"
    __table_args__ = (UniqueConstraint("version_id", "name"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("versions.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[float] = mapped_column(Float, index=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)
    samples: Mapped[list[dict[str, JsonValue]]] = mapped_column(JSON)


def install_training_constraints(connection: Connection, *, sqlite: bool) -> None:
    """Reject mutations to saved splits and to source manifests used by saved splits."""
    if sqlite:
        for operation in ("UPDATE", "DELETE"):
            connection.execute(
                text(
                    f"CREATE TRIGGER IF NOT EXISTS training_no_{operation.lower()} "
                    f"BEFORE {operation} ON training_splits BEGIN "
                    "SELECT RAISE(ABORT, 'training splits are immutable'); END"
                )
            )
        connection.execute(
            text(
                "CREATE TRIGGER IF NOT EXISTS training_version_no_update "
                "BEFORE UPDATE OF manifest, dataset_id, id ON versions "
                "WHEN EXISTS (SELECT 1 FROM training_splits WHERE version_id = OLD.id) "
                "BEGIN SELECT RAISE(ABORT, 'training source versions are immutable'); END"
            )
        )
    else:
        connection.execute(
            text(
                "CREATE OR REPLACE FUNCTION datakeel_immutable_training() RETURNS trigger AS $$ "
                "BEGIN RAISE EXCEPTION 'training splits are immutable'; END; $$ LANGUAGE plpgsql"
            )
        )
        ensure_pg_trigger(
            connection,
            name="training_immutable",
            table="training_splits",
            event="UPDATE OR DELETE",
            function="datakeel_immutable_training",
        )
        connection.execute(
            text(
                "CREATE OR REPLACE FUNCTION datakeel_training_version() RETURNS trigger AS $$ "
                "BEGIN IF EXISTS (SELECT 1 FROM training_splits WHERE version_id = OLD.id) "
                "AND (NEW.manifest::text IS DISTINCT FROM OLD.manifest::text "
                "OR NEW.dataset_id IS DISTINCT FROM OLD.dataset_id "
                "OR NEW.id IS DISTINCT FROM OLD.id) "
                "THEN RAISE EXCEPTION 'training source versions are immutable'; END IF; "
                "RETURN NEW; END; $$ LANGUAGE plpgsql"
            )
        )
        ensure_pg_trigger(
            connection,
            name="training_version_immutable",
            table="versions",
            event="UPDATE",
            function="datakeel_training_version",
        )
