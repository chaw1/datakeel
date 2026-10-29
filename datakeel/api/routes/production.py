# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read production facts; all mutations use the existing controlled action endpoints."""

import io
import mimetypes
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, Response
from PIL import Image

from datakeel.api.dependencies import DatabaseDependency
from datakeel.api.identity_access import http_actor
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import NotFoundError
from datakeel.core.models import JsonDocument
from datakeel.core.production_reads import (
    ProductionKind,
    ProductionObjectFilters,
    ProductionObjectQuery,
)
from datakeel.core.workbench_models import (
    WorkbenchIndex,
    WorkbenchProject,
    WorkbenchProjectQuery,
    WorkbenchTask,
)
from datakeel.ontology.functions import invoke_function
from datakeel.ontology.models import FunctionResult
from datakeel.ontology.production_functions import PRODUCTION_READ_MODELS
from datakeel.storage.workbench_reads import (
    task_source,
    workbench_index,
    workbench_project,
    workbench_task,
)

router = APIRouter(prefix="/api/production", tags=["production"])


def _caller(request: Request) -> AccessContext:
    return AccessContext(actor=http_actor(request), entry="ask", scope="query")


@router.get("/workbench")
def workbench(db: DatabaseDependency, request: Request) -> WorkbenchIndex:
    """Discover readable production projects and the server-selected human identity."""
    return workbench_index(db, _caller(request))


@router.get("/projects/{project_id}/workbench")
def project_workbench(
    project_id: str,
    query: Annotated[WorkbenchProjectQuery, Query()],
    db: DatabaseDependency,
    request: Request,
) -> WorkbenchProject:
    """Read exact production configuration, role scopes, measurements and a task page."""
    return workbench_project(db, project_id, _caller(request), query)


@router.get("/tasks/{task_id}/workbench")
def task_workbench(task_id: str, db: DatabaseDependency, request: Request) -> WorkbenchTask:
    """Read one sample with its complete revision, assignment and review evidence."""
    return workbench_task(db, task_id, _caller(request))


@router.get("/tasks/{task_id}/content", response_model=None)
def task_content(
    task_id: str, db: DatabaseDependency, request: Request, *, thumbnail: bool = False
) -> FileResponse | Response:
    """View a version-pinned source or a small image preview under the same source grants."""
    path, name = task_source(db, task_id, _caller(request))
    if thumbnail:
        with Image.open(path) as image:
            preview = image.convert("RGB")
            preview.thumbnail((1024, 1024))
            output = io.BytesIO()
            preview.save(output, "JPEG", quality=80)
        return Response(output.getvalue(), media_type="image/jpeg")
    media_type = mimetypes.guess_type(name)[0]
    if media_type is not None and media_type.startswith("image/"):
        with Image.open(path) as image:
            if image.getexif().get(274) not in (None, 1):
                output = io.BytesIO()
                image.save(output, "PNG", exif=b"")
                return Response(output.getvalue(), media_type="image/png")
    return FileResponse(path, media_type=mimetypes.guess_type(name)[0], filename=name)


@router.post("/functions/{name}")
def read_function(
    name: str, body: JsonDocument, db: DatabaseDependency, request: Request
) -> FunctionResult:
    """Read progress, workload, rework, agreement, confidence, labels and next task."""
    if name not in PRODUCTION_READ_MODELS:
        message = "Unknown production read function"
        raise NotFoundError(message)
    return invoke_function(db, name, body, access=_caller(request))


@router.get("/objects/{kind}")
def objects(
    kind: ProductionKind,
    filters: Annotated[ProductionObjectFilters, Query()],
    db: DatabaseDependency,
    request: Request,
) -> FunctionResult:
    """Project registered people and production objects with their exact AssetRef identity."""
    selection = ProductionObjectQuery(
        kind=kind,
        **filters.model_dump(),
    )
    return invoke_function(
        db,
        "production_objects",
        JsonDocument(selection.model_dump(mode="json")),
        access=_caller(request),
    )
