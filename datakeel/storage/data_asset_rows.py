# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Asset fact tables and immutable audit database constraints."""

from pydantic import JsonValue
from sqlalchemy import JSON, Float, ForeignKey, String, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base


class DataAssetRow(Base):
    """Store the current controlled asset revision as a typed JSON snapshot."""

    __tablename__ = "data_assets"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class DataAssetHistoryRow(Base):
    """Append a complete snapshot under one globally unique operation identity."""

    __tablename__ = "data_asset_history"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("data_assets.id"), index=True)
    operation_id: Mapped[str] = mapped_column(String, unique=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class AssetApplicationRow(Base):
    """Store applications separately from the protected usage ledger."""

    __tablename__ = "asset_applications"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("data_assets.id"), index=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class AssetGrantRow(Base):
    """Store revocable grants with one grant per approved application."""

    __tablename__ = "asset_grants"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("data_assets.id"), index=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("asset_applications.id"), unique=True)
    subject: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class AssetUsageRow(Base):
    """Persist allowed reads as immutable individual asset uses."""

    __tablename__ = "asset_usage"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("data_assets.id"), index=True)
    actor: Mapped[str] = mapped_column(String, index=True)
    occurred_at: Mapped[float] = mapped_column(Float, index=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class AssetControlRow(Base):
    """Append every submitted application and controlled decision."""

    __tablename__ = "asset_control_events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("data_assets.id"), index=True)
    operation_id: Mapped[str] = mapped_column(String, unique=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


def install_asset_constraints(connection: Connection, *, sqlite: bool) -> None:
    """Reject UPDATE and DELETE even through direct SQL on immutable ledgers."""
    tables = ("asset_usage", "data_asset_history", "asset_control_events")
    if not sqlite:
        connection.execute(
            text("""
            CREATE OR REPLACE FUNCTION datakeel_immutable_asset() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'asset audit records are append-only'; END;
            $$ LANGUAGE plpgsql
        """)
        )
    for table in tables:
        if sqlite:
            for operation in ("UPDATE", "DELETE"):
                connection.execute(
                    text(
                        f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} "
                        f"BEFORE {operation} ON {table} BEGIN "
                        "SELECT RAISE(ABORT, 'asset audit records are append-only'); END"
                    )
                )
        else:
            connection.execute(text(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}"))
            connection.execute(
                text(
                    f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                    "FOR EACH ROW EXECUTE FUNCTION datakeel_immutable_asset()"
                )
            )
