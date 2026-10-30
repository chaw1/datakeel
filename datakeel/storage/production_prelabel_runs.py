# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared prelabel run records: target tasks, pinned sample sizes and the persisted run."""

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.models import FileItem, new_id, utcnow
from datakeel.core.production_catalog_models import (
    PredictionFailure,
    PrelabelRun,
    ProductionModel,
)
from datakeel.core.production_models import Project
from datakeel.core.production_prediction_models import PredictionSample
from datakeel.storage.annotation_store import require_annotation_version
from datakeel.storage.production_catalog_rows import ProductionPrelabelRunRow
from datakeel.storage.production_rows import ProductionTaskRow


def prediction_tasks(
    session: Session,
    project_id: str,
    package_id: str | None = None,
) -> list[ProductionTaskRow]:
    """Select only tasks owned by the exact project and optional package."""
    statement = select(ProductionTaskRow).where(ProductionTaskRow.project_id == project_id)
    if package_id is not None:
        statement = statement.where(ProductionTaskRow.package_id == package_id)
    return list(session.scalars(statement.order_by(ProductionTaskRow.id).with_for_update()))


def _dimension(metadata: dict[str, JsonValue], name: str) -> float | None:
    value = metadata.get(name, metadata.get("image_" + name))
    return (
        float(value)
        if isinstance(value, int | float) and not isinstance(value, bool) and value > 0
        else None
    )


def prediction_samples(session: Session, project: Project) -> tuple[PredictionSample, ...]:
    """Read dimensions from the project's pinned immutable manifest."""
    version = require_annotation_version(session, project.dataset_id, project.version_id)
    files = [FileItem.model_validate(item) for item in version.manifest]
    return tuple(
        PredictionSample(
            id=item.id,
            filename=item.filename,
            width=_dimension(item.metadata, "width"),
            height=_dimension(item.metadata, "height"),
        )
        for item in files
    )


def new_run(project_id: str, package_id: str | None, model: ProductionModel) -> PrelabelRun:
    """Start a run record attributed to the exact model identity and provider."""
    return PrelabelRun(
        id=new_id(),
        project_id=project_id,
        package_id=package_id,
        model_id=model.id,
        model_name=model.name,
        model_version=model.version,
        revision_ids=(),
        confidences=(),
        cost=0,
        elapsed_seconds=0,
        created_at=utcnow(),
        provider=model.provider,
        currency=model.currency,
    )


def save_run(
    session: Session,
    run: PrelabelRun,
    revision_ids: list[str],
    failures: list[PredictionFailure],
    confidences: list[float],
    *,
    cost: float,
) -> PrelabelRun:
    """Persist the run with its outputs, failures, measured cost and elapsed time."""
    value = run.model_copy(
        update={
            "revision_ids": tuple(revision_ids),
            "failures": tuple(failures),
            "confidences": tuple(confidences),
            "cost": cost,
            "elapsed_seconds": (utcnow() - run.created_at).total_seconds(),
        }
    )
    session.add(
        ProductionPrelabelRunRow(
            id=value.id, project_id=value.project_id, payload=value.model_dump(mode="json")
        )
    )
    return value
