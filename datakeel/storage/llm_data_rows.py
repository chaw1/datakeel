# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist immutable training reports and registered evaluation snapshots."""

from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from datakeel.core.models import new_id, utcnow
from datakeel.storage.base import Base


class TrainingEvaluationRow(Base):
    """Retain the exact uploaded evaluation files and their content fingerprints."""

    __tablename__ = "training_evaluations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class TrainingRunRow(Base):
    """Keep a version-scoped dry run, private source references and immutable ledger key."""

    __tablename__ = "training_governance_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("versions.id"), index=True)
    created_at: Mapped[float] = mapped_column(Float, default=lambda: utcnow().timestamp())
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    file_ids: Mapped[list[str]] = mapped_column(JSON)
    evaluation_ids: Mapped[list[str]] = mapped_column(JSON)
    ledger_key: Mapped[str] = mapped_column(String)


class TrainingCleanRow(Base):
    """Map one approved dry run to exactly one published clean version."""

    __tablename__ = "training_clean_versions"
    run_id: Mapped[str] = mapped_column(ForeignKey("training_governance_runs.id"), primary_key=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("versions.id"), unique=True)
