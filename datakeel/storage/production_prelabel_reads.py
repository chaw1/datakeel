# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Project-page reads: prelabel spend per model, run progress and the effective thresholds."""

from decimal import Decimal

from sqlalchemy import select

from datakeel.core.prelabel_models import (
    AIReview,
    ConfidenceThresholds,
    ModelSpend,
    PrelabelProgress,
)
from datakeel.core.production_catalog_models import PrelabelRun
from datakeel.core.production_models import Project
from datakeel.storage.database import Database
from datakeel.storage.production_ai_rows import latest_reviews
from datakeel.storage.production_catalog_rows import ProductionPrelabelRunRow
from datakeel.storage.production_tiers import project_thresholds


def prelabel_spend(db: Database, project_id: str) -> tuple[ModelSpend, ...]:
    """Total every run's measured tokens and cost per model on one project."""
    totals: dict[str, ModelSpend] = {}
    costs: dict[str, Decimal] = {}
    with db.session() as session:
        rows = session.scalars(
            select(ProductionPrelabelRunRow).where(
                ProductionPrelabelRunRow.project_id == project_id
            )
        )
        runs = [PrelabelRun.model_validate(row.payload) for row in rows]
    for run in sorted(runs, key=lambda item: (item.created_at, item.id)):
        current = totals.get(run.model_id) or ModelSpend(
            model_id=run.model_id,
            model_name=run.model_name,
            model_version=run.model_version,
            currency=run.currency or "",
            runs=0,
            images=0,
            input_tokens=0,
            output_tokens=0,
            cost=0,
        )
        costs[run.model_id] = costs.get(run.model_id, Decimal(0)) + Decimal(str(run.cost))
        totals[run.model_id] = current.model_copy(
            update={
                "model_name": run.model_name,
                "model_version": run.model_version,
                "currency": run.currency or current.currency,
                "runs": current.runs + 1,
                "images": current.images + len(run.revision_ids) + len(run.failures),
                "input_tokens": current.input_tokens + run.input_tokens,
                "output_tokens": current.output_tokens + run.output_tokens,
                "cost": float(costs[run.model_id]),
            }
        )
    return tuple(sorted(totals.values(), key=lambda item: (-item.cost, item.model_id)))


def prelabel_progress(
    db: Database, project_id: str, limit: int = 5
) -> tuple[PrelabelProgress, ...]:
    """Show the newest cloud runs, running ones first, as images done, failed and money spent."""
    with db.session() as session:
        rows = session.scalars(
            select(ProductionPrelabelRunRow).where(
                ProductionPrelabelRunRow.project_id == project_id,
                ProductionPrelabelRunRow.payload["provider"].as_string() == "cloud",
            )
        )
        runs = [PrelabelRun.model_validate(row.payload) for row in rows]
    runs.sort(key=lambda run: (run.status != "running", -run.created_at.timestamp(), run.id))
    return tuple(
        PrelabelProgress(
            run_id=run.id,
            model_id=run.model_id,
            model_name=run.model_name,
            model_version=run.model_version,
            status=run.status,
            planned_images=run.planned_images,
            completed_images=run.completed_images,
            failed_images=run.failed_images,
            spent=run.cost,
            budget=run.budget,
            currency=run.currency,
            stopped=run.stopped is not None,
            started_at=run.created_at,
            updated_at=run.updated_at,
        )
        for run in runs[:limit]
    )


def project_confidence_thresholds(db: Database, project: Project) -> ConfidenceThresholds:
    """Return the thresholds a new run would use, with their measured basis."""
    with db.session() as session:
        return project_thresholds(session, project)


def task_ai_review(db: Database, task_id: str) -> AIReview | None:
    """Return the task's newest AI pre-review, whichever revision it scored."""
    with db.session() as session:
        return latest_reviews(session, (task_id,)).get(task_id)
