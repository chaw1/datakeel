# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Internal rows for replayable evidence, append-only decisions, and cache slots."""

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base


class AssertionRow(Base):
    """Persist immutable observation content and mutable reviewed-state overlays."""

    __tablename__ = "assertions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    subject_id: Mapped[str] = mapped_column(String, index=True)
    predicate: Mapped[str] = mapped_column(String, index=True)
    producer_event_id: Mapped[str] = mapped_column(ForeignKey("lineage_events.event_id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="candidate")
    decided_by: Mapped[str | None] = mapped_column(String, nullable=True)
    decided_at: Mapped[str | None] = mapped_column(String, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    verification: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    verification_detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class AssertionDecisionRow(Base):
    """Keep human decisions and extractor invalidation history independently."""

    __tablename__ = "assertion_decisions"
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String, unique=True)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True)
    assertion_id: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class EvidenceCacheRow(Base):
    """Store a disposable content cache projection for one logical extractor slot."""

    __tablename__ = "evidence_cache"
    slot: Mapped[str] = mapped_column(String, primary_key=True)
    cache_key: Mapped[str] = mapped_column(String, index=True)
    producer_event_id: Mapped[str] = mapped_column(ForeignKey("lineage_events.event_id"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
