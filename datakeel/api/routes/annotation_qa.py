# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Version-scoped annotation metrics, reproducible sampling and repair exports."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response

from datakeel.actions.models import ActionPlan
from datakeel.actions.service import prepare_action
from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.annotation_sampling import (
    AnnotationAcceptanceParams,
    AnnotationImportRequest,
    AnnotationQualityOverview,
    AnnotationQualityReport,
    SamplingPlan,
    SamplingRequest,
)
from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument
from datakeel.storage.annotation_rework import export_rework
from datakeel.storage.annotation_sampling import create_sampling_plan
from datakeel.storage.annotation_store import (
    get_annotation_quality,
    import_annotations,
)

router = APIRouter(
    prefix="/api/datasets/{dataset_id}/annotation-quality", tags=["annotation quality"]
)


@router.get("")
def overview(
    dataset_id: str, db: DatabaseDependency, version_id: str | None = None
) -> AnnotationQualityOverview:
    """Read metrics, findings, repair comparisons and approved inspection history."""
    return get_annotation_quality(db, dataset_id, version_id)


@router.post("/batches", status_code=201)
def import_batch(
    dataset_id: str, body: AnnotationImportRequest, db: DatabaseDependency
) -> AnnotationQualityReport:
    """Append a frozen imported annotation batch; acceptance is a separate signed action."""
    return import_annotations(db, dataset_id, body)


@router.post("/samples", status_code=201)
def sample(dataset_id: str, body: SamplingRequest, db: DatabaseDependency) -> SamplingPlan:
    """Freeze reproducible unit selection without declaring acceptance or rejection."""
    return create_sampling_plan(db, dataset_id, body)


@router.get(
    "/rework/{batch_id}",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}, "application/json": {}}}},
)
def rework_export(
    dataset_id: str,
    batch_id: str,
    db: DatabaseDependency,
    export_format: Annotated[Literal["json", "csv"], Query(alias="format")] = "json",
) -> Response:
    """Export suspected errors and signed rejected-unit details for a repair review."""
    content = export_rework(db, dataset_id, batch_id, csv_format=export_format == "csv")
    return Response(
        content,
        media_type="text/csv" if export_format == "csv" else "application/json",
        headers={
            "Content-Disposition": f'attachment; filename="annotation-rework.{export_format}"'
        },
    )


@router.post("/acceptance/prepare")
def prepare_acceptance(
    dataset_id: str, body: AnnotationAcceptanceParams, db: DatabaseDependency
) -> ActionPlan:
    """Prepare a typed inspection plan whose approval and execution use existing actions."""
    if body.dataset_id != dataset_id:
        message = "Inspection dataset does not match the request path"
        raise ValidationError(message)
    return prepare_action(
        db, "annotation_acceptance", JsonDocument.model_validate(body.model_dump(mode="json"))
    )
