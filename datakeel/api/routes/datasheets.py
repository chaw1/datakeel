# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Versioned, cited dataset documentation and controlled draft/publication plans."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response

from datakeel.actions.datasheet_parameters import GenerateDatasheetRequest
from datakeel.actions.models import ActionPlan
from datakeel.actions.service import prepare_action
from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.datasheet_execution import DatasheetJob
from datakeel.core.datasheet_models import DatasheetComparison, DatasheetDocument
from datakeel.core.models import JsonDocument
from datakeel.datasheets.render import render_html, render_markdown
from datakeel.storage.datasheet_jobs import get_job
from datakeel.storage.datasheet_store import compare_documents, get_document, list_documents

router = APIRouter(prefix="/api", tags=["datasheets"])


@router.get("/datasets/{dataset_id}/datasheets")
def documents(
    dataset_id: str,
    db: DatabaseDependency,
    version_id: str | None = None,
) -> tuple[DatasheetDocument, ...]:
    """List frozen drafts with their current version-expiry marker."""
    return list_documents(db, dataset_id, version_id)


@router.post("/datasets/{dataset_id}/datasheets")
def generate(
    dataset_id: str,
    body: GenerateDatasheetRequest,
    db: DatabaseDependency,
) -> ActionPlan:
    """Freeze actual facts into a draft action; external model calls require approval."""
    return prepare_action(
        db,
        "generate_datasheet",
        JsonDocument.model_validate({**body.model_dump(mode="json"), "dataset_id": dataset_id}),
    )


@router.get("/datasheets/jobs/{job_id}")
def job(job_id: str, db: DatabaseDependency) -> DatasheetJob:
    """Read queued, complete, failed or cancelled optional model generation."""
    return get_job(db, job_id)


@router.get("/datasheets/{document_id}")
def document(document_id: str, db: DatabaseDependency) -> DatasheetDocument:
    """Read one immutable cited document with current publication and expiry state."""
    return get_document(db, document_id)


@router.post("/datasheets/{document_id}/publish")
def publish(document_id: str, db: DatabaseDependency) -> ActionPlan:
    """Prepare publication for explicit review through the existing approval gate."""
    value = get_document(db, document_id)
    return prepare_action(
        db,
        "publish_datasheet",
        JsonDocument({"dataset_id": value.dataset_id, "document_id": value.id}),
    )


@router.get("/datasheets/{before_id}/compare/{after_id}")
def compare(before_id: str, after_id: str, db: DatabaseDependency) -> DatasheetComparison:
    """Compare frozen fact values between two saved snapshots of the same dataset."""
    return compare_documents(db, before_id, after_id)


@router.get(
    "/datasheets/{document_id}/download",
    response_class=Response,
    responses={200: {"content": {"text/markdown": {}, "text/html": {}}}},
)
def download(
    document_id: str,
    db: DatabaseDependency,
    output_format: Annotated[Literal["markdown", "html"], Query(alias="format")] = "markdown",
) -> Response:
    """Download escaped Markdown or standalone HTML with sentence-level fact links."""
    value = get_document(db, document_id)
    html = output_format == "html"
    content = render_html(value) if html else render_markdown(value)
    suffix = "html" if html else "md"
    return Response(
        content,
        media_type="text/html" if html else "text/markdown",
        headers={"Content-Disposition": f'attachment; filename="datasheet-{value.id}.{suffix}"'},
    )
