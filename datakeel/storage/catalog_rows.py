# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Disposable metadata projections; append-only lineage events remain authoritative."""

from pydantic import JsonValue
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base


class CatalogObjectRow(Base):
    """Project the latest object owned by one metadata import scope."""

    __tablename__ = "catalog_objects"
    asset_id: Mapped[str] = mapped_column(String, primary_key=True)
    scope: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


class CatalogEdgeRow(Base):
    """Keep catalog relationships separate from lineage and semantic assertion edges."""

    __tablename__ = "catalog_edges"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    scope: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String, index=True)
    source_id: Mapped[str] = mapped_column(String, index=True)
    target_id: Mapped[str] = mapped_column(String, index=True)
    producer_event_id: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)
