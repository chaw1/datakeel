# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared prelabel run records: target tasks, pinned sample sizes and the persisted run."""

from datetime import timedelta

from pydantic import JsonValue
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from datakeel.core.errors import ConflictError, NotFoundError
from datakeel.core.models import AssetRef, FileItem, new_id, utcnow
from datakeel.core.production_catalog_models import (
    PredictionFailure,
    PrelabelRun,
    ProductionModel,
)
from datakeel.core.production_models import Project
from datakeel.core.production_prediction_models import PredictionSample
from datakeel.storage.action_rows import ActionRunRow
from datakeel.storage.annotation_store import require_annotation_version
from datakeel.storage.image_geometry import file_geometry
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
    """Read upright dimensions from the project's pinned immutable manifest."""
    version = require_annotation_version(session, project.dataset_id, project.version_id)
    files = [FileItem.model_validate(item) for item in version.manifest]
    return tuple(_prediction_sample(item) for item in files)


def _prediction_sample(item: FileItem) -> PredictionSample:
    geometry = file_geometry(item)
    if geometry is None:
        return PredictionSample(
            id=item.id,
            filename=item.filename,
            width=_dimension(item.metadata, "width"),
            height=_dimension(item.metadata, "height"),
        )
    return PredictionSample(
        id=item.id,
        filename=item.filename,
        width=geometry.width,
        height=geometry.height,
        geometry=geometry,
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


def prelabel_outputs(run: PrelabelRun) -> list[AssetRef]:
    """Name the run record and every draft it wrote as the action's outputs."""
    return [
        AssetRef(asset_type="prelabel_run", asset_id=run.id),
        *(
            AssetRef(asset_type="annotation_revision", asset_id=identifier)
            for identifier in run.revision_ids
        ),
    ]


# A running cloud run writes its progress after every batch of images; one silent this long
# belongs to a process that died, and the next run may take the project's slot over.
STALE_AFTER = timedelta(minutes=10)


def locked_run(session: Session, run_id: str) -> tuple[ProductionPrelabelRunRow, PrelabelRun]:
    """Lock one run record so progress and the final state are written by one writer."""
    row = session.scalar(
        select(ProductionPrelabelRunRow)
        .where(ProductionPrelabelRunRow.id == run_id)
        .with_for_update()
    )
    if row is None:
        message = "Prelabel run not found"
        raise NotFoundError(message)
    return row, PrelabelRun.model_validate(row.payload)


def store_run(row: ProductionPrelabelRunRow, run: PrelabelRun) -> None:
    """Replace the run record's payload with its newer state."""
    row.payload = run.model_dump(mode="json")


def claim_run_slot(session: Session, project_id: str) -> None:
    """Refuse a second live cloud run on one project; mark a silent one abandoned instead.

    Two runs over the same tasks would pay twice for the same images, so only one may be
    running. Its action attempt is closed as failed when its run is taken over.
    """
    now = utcnow()
    for row in session.scalars(
        select(ProductionPrelabelRunRow)
        .where(
            ProductionPrelabelRunRow.project_id == project_id,
            ProductionPrelabelRunRow.payload["status"].as_string() == "running",
        )
        .with_for_update()
    ):
        run = PrelabelRun.model_validate(row.payload)
        if now - (run.updated_at or run.created_at) < STALE_AFTER:
            message = (
                "A cloud prelabel run is already in progress for this project "
                f"({run.completed_images + run.failed_images} of {run.planned_images} images)"
            )
            raise ConflictError(message)
        store_run(row, run.model_copy(update={"status": "abandoned", "updated_at": now}))
        if run.plan_id is not None:
            session.execute(
                update(ActionRunRow)
                .where(ActionRunRow.plan_id == run.plan_id, ActionRunRow.status == "RUNNING")
                .values(
                    status="FAILED",
                    error="Abandoned: the run stopped reporting progress",
                    completed_at=now.timestamp(),
                )
            )
