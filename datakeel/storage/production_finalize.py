# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Finalize approved production revisions using the existing version-owned annotation importer."""

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.actions.models import OperationResult
from datakeel.actions.production_catalog_parameters import FinalizeProjectParams
from datakeel.core.annotation_models import AnnotationBatch
from datakeel.core.annotation_sampling import AnnotationImportRequest
from datakeel.core.errors import ConflictError
from datakeel.core.models import AssetRef, FileItem, JsonDocument, new_id
from datakeel.core.production_models import AnnotationRevision
from datakeel.storage.annotation_store import (
    import_annotations_in_session,
    require_annotation_version,
)
from datakeel.storage.database import VersionRow
from datakeel.storage.production_catalog import annotation_categories
from datakeel.storage.production_rows import (
    ProductionProjectRow,
    ProductionRevisionRow,
    ProductionTaskRow,
)
from datakeel.storage.production_tasks import require_mutable_project, transition_task


def finalize_project(session: Session, params: FinalizeProjectParams) -> OperationResult:
    """Atomically publish a new dataset version, annotation batch and finalized task states."""
    project_row = session.get(
        ProductionProjectRow,
        params.project_id,
        with_for_update=True,
        populate_existing=True,
    )
    project = require_mutable_project(session, params.project_id)
    tasks = _final_tasks(session, project.id)
    revisions = _approved_revisions(session, tasks)
    source = require_annotation_version(session, project.dataset_id, project.version_id)
    version = VersionRow(
        id=new_id(),
        dataset_id=project.dataset_id,
        manifest=_final_manifest(source, revisions, project.id),
    )
    session.add(version)
    session.flush()
    report = import_annotations_in_session(
        session,
        project.dataset_id,
        AnnotationImportRequest(
            version_id=version.id,
            batch=AnnotationBatch(annotations=tuple(item.annotation for item in revisions)),
            idempotency_key=f"production:{project.id}:{params.request_id}",
            name=params.name,
        ),
    )
    if project_row is not None:
        project_row.payload = project.model_copy(
            update={
                "finalized_version_id": version.id,
            }
        ).model_dump(mode="json")
    for task in tasks:
        transition_task(session, task, "finalized")
    return OperationResult(
        outputs=[
            AssetRef(asset_type="version", asset_id=version.id, version=version.id),
            AssetRef(asset_type="annotation_batch", asset_id=report.id, version=version.id),
        ],
        details={
            "project_id": project.id,
            "produced_by_project": project.id,
            "dataset_id": project.dataset_id,
            "source_version_id": source.id,
            "version_id": version.id,
            "batch_id": report.id,
            "revision_ids": [revision.id for revision in revisions],
        },
    )


def _final_tasks(session: Session, project_id: str) -> list[ProductionTaskRow]:
    tasks = list(
        session.scalars(
            select(ProductionTaskRow)
            .where(ProductionTaskRow.project_id == project_id)
            .order_by(ProductionTaskRow.id)
            .with_for_update()
        )
    )
    if not tasks or any(
        task.state != "approved" or task.approved_revision_id is None for task in tasks
    ):
        message = "Every project task must have an approved revision before finalization"
        raise ConflictError(message)
    return tasks


def _approved_revisions(
    session: Session, tasks: list[ProductionTaskRow]
) -> tuple[AnnotationRevision, ...]:
    revisions: list[AnnotationRevision] = []
    for task in tasks:
        row = session.get(ProductionRevisionRow, task.approved_revision_id)
        if row is None or row.task_id != task.id:
            message = "Approved revision does not belong to its production task"
            raise ConflictError(message)
        revisions.append(AnnotationRevision.model_validate(row.payload))
    return tuple(revisions)


def _final_manifest(
    source: VersionRow,
    revisions: tuple[AnnotationRevision, ...],
    project_id: str,
) -> list[dict[str, JsonValue]]:
    by_sample = {revision.annotation.sample_id: revision for revision in revisions}
    result: list[dict[str, JsonValue]] = []
    for raw in source.manifest:
        item = FileItem.model_validate(raw)
        revision = by_sample.get(item.id)
        if revision is None:
            message = "Every source file must have an approved production revision"
            raise ConflictError(message)
        categories = annotation_categories(revision.annotation)
        metadata = {
            key: value
            for key, value in JsonDocument.model_validate(item.metadata).root.items()
            if key not in {"annotations", "annotation", "labels", "label"}
        }
        metadata.update(
            JsonDocument.model_validate(
                {
                    "annotation": revision.annotation.model_dump(mode="json"),
                    "annotation_count": len(categories),
                    "labels": sorted(set(categories)),
                    "label_count": len(set(categories)),
                    "production": {
                        "project_id": project_id,
                        "revision_id": revision.id,
                        "source": revision.source,
                        "model_name": revision.model_name,
                        "model_version": revision.model_version,
                        "confidence": revision.confidence,
                    },
                }
            ).root
        )
        result.append(
            JsonDocument.model_validate(
                item.model_copy(update={"metadata": metadata}).model_dump(mode="json")
            ).root
        )
    return result
