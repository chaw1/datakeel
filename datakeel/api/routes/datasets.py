# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Dataset imports, immutable versions, and file downloads."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse

from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.file_queries import FileQuery
from datakeel.storage import dataset_service as service
from datakeel.storage.dataset_service import DatasetInput
from datakeel.storage.governance_service import dataset_quality_summaries
from datakeel.storage.views import DatasetQualityView, DatasetView, FileView, VersionView

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.get("")
def datasets(
    db: DatabaseDependency, request: Request, include: Literal["quality"] | None = None
) -> list[DatasetView | DatasetQualityView]:
    """List datasets, optionally including the latest read-only quality score."""
    return (
        list(dataset_quality_summaries(db, access=_query_access(request)))
        if include
        else list(service.list_datasets(db))
    )


@router.post("", status_code=201)
def create_dataset(body: DatasetInput, db: DatabaseDependency) -> DatasetView:
    """Import uploaded files and their initial immutable manifest."""
    return service.create_dataset(db, body)


@router.get("/{identifier}")
def dataset(identifier: str, db: DatabaseDependency) -> DatasetView:
    """Read one dataset summary."""
    return service.get_dataset(db, identifier)


@router.get("/{identifier}/files")
def files(
    identifier: str,
    db: DatabaseDependency,
    request: Request,
    query: Annotated[FileQuery, Query()],
    version: str | None = None,
) -> list[FileView]:
    """Read original or versioned files without exposing local paths."""
    return service.list_files(db, identifier, version, access=_query_access(request), query=query)


@router.get("/{identifier}/versions")
def versions(identifier: str, db: DatabaseDependency, request: Request) -> list[VersionView]:
    """List a dataset's immutable manifest snapshots."""
    return service.list_versions(db, identifier, access=_query_access(request))


@router.get("/{identifier}/files/{file_id}/download")
def download(
    identifier: str,
    file_id: str,
    request: Request,
    db: DatabaseDependency,
    version: Annotated[str | None, Query(min_length=1)] = None,
) -> FileResponse:
    """Download a file from its dataset, optionally pinned to one immutable version."""
    value = service.resolve_download(
        db,
        identifier,
        file_id,
        version,
        access=AccessContext(
            actor=request.headers.get("X-Datakeel-Actor", "local-user"),
            entry="download",
            scope="download",
        ),
    )
    return FileResponse(value.path, filename=value.filename)


def _query_access(request: Request) -> AccessContext:
    return AccessContext(
        actor=request.headers.get("X-Datakeel-Actor", "local-user"), entry="ask", scope="query"
    )


@router.get(
    "/{identifier}/files/{file_id}/pointcloud-preview",
    response_class=FileResponse,
    responses={200: {"content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}}},
)
def pointcloud_preview(
    identifier: str,
    file_id: str,
    request: Request,
    db: DatabaseDependency,
    version: Annotated[str | None, Query(min_length=1)] = None,
) -> FileResponse:
    """View a PNG preview from the same dataset/version scope as its point cloud."""
    value = service.resolve_pointcloud_preview(
        db,
        identifier,
        file_id,
        version,
        access=AccessContext(
            actor=request.headers.get("X-Datakeel-Actor", "local-user"),
            entry="download",
            scope="download",
        ),
    )
    return FileResponse(value.path, media_type="image/png", filename=value.filename)
