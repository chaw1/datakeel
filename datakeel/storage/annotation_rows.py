# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Append-only annotation batches, sample plans and signed inspection history."""

from pydantic import JsonValue
from sqlalchemy import JSON, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.storage.base import Base


class AnnotationBatchRow(Base):
    """Keep imported annotation inputs separate from frozen calculated reports."""

    __tablename__ = "annotation_batches"
    __table_args__ = (UniqueConstraint("dataset_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("versions.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String)
    request_digest: Mapped[str] = mapped_column(String)
    batch: Mapped[dict[str, JsonValue]] = mapped_column(JSON)
    report: Mapped[dict[str, JsonValue]] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, index=True)
    # NULL marks batches imported before v0.19 in the stored pixel frame; new ones say "display".
    coordinate_frame: Mapped[str | None] = mapped_column(String, nullable=True)


class AnnotationSamplingRow(Base):
    """Persist reproducible selection before any inspection can be approved."""

    __tablename__ = "annotation_sampling_plans"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("annotation_batches.id"), index=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, index=True)


class AnnotationInspectionRow(Base):
    """Retain every approved acceptance decision with its controlling plan identity."""

    __tablename__ = "annotation_inspections"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    action_plan_id: Mapped[str] = mapped_column(ForeignKey("action_plans.id"), unique=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("annotation_batches.id"), index=True)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, index=True)
