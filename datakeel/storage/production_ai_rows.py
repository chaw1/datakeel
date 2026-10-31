# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Append-only AI pre-review facts bound to the exact submitted revision."""

from pydantic import JsonValue
from sqlalchemy import JSON, Float, ForeignKey, String, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Session, mapped_column

from datakeel.core.prelabel_models import AIReview
from datakeel.storage.base import Base
from datakeel.storage.pg_triggers import ensure_pg_trigger


class ProductionAIReviewRow(Base):
    """Keep every risk score, its reasons and the sampling decision for audit."""

    __tablename__ = "production_ai_reviews"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("production_tasks.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("production_projects.id"), index=True)
    revision_id: Mapped[str] = mapped_column(String, index=True)
    risk: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict[str, JsonValue]] = mapped_column(JSON)


def install_ai_review_constraints(connection: Connection, *, sqlite: bool) -> None:
    """Reject updates and deletes so an exemption can never be rewritten after the fact."""
    if sqlite:
        for operation in ("UPDATE", "DELETE"):
            connection.execute(
                text(
                    "CREATE TRIGGER IF NOT EXISTS "
                    f"production_ai_reviews_no_{operation.lower()} BEFORE {operation} ON "
                    "production_ai_reviews BEGIN "
                    "SELECT RAISE(ABORT, 'production history is append-only'); END"
                )
            )
        return
    ensure_pg_trigger(
        connection,
        name="production_ai_reviews_immutable",
        table="production_ai_reviews",
        event="UPDATE OR DELETE",
        function="datakeel_immutable_production",
    )


def latest_reviews(session: Session, task_ids: tuple[str, ...]) -> dict[str, AIReview]:
    """Return each task's newest AI pre-review, keyed by task."""
    result: dict[str, AIReview] = {}
    if not task_ids:
        return result
    for row in session.scalars(
        select(ProductionAIReviewRow).where(ProductionAIReviewRow.task_id.in_(task_ids))
    ):
        review = AIReview.model_validate(row.payload)
        current = result.get(review.task_id)
        if current is None or (review.created_at, review.id) > (current.created_at, current.id):
            result[review.task_id] = review
    return result
