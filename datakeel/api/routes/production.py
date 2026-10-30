# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read production facts; all mutations use the existing controlled action endpoints."""

import mimetypes
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, Response

from datakeel.api.dependencies import DatabaseDependency
from datakeel.api.identity_access import http_actor
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import NotFoundError
from datakeel.core.models import JsonDocument
from datakeel.core.production_models import AssignmentStage
from datakeel.core.production_reads import (
    ProductionKind,
    ProductionObjectFilters,
    ProductionObjectQuery,
)
from datakeel.core.workbench_models import (
    SkillDispatchPreview,
    SkillDispatchPreviewRequest,
    WorkbenchAssignees,
    WorkbenchIndex,
    WorkbenchProject,
    WorkbenchProjectQuery,
    WorkbenchTask,
    WorkbenchTaskSampleQuery,
    WorkbenchTaskSamples,
    WorkbenchTaskStatus,
)
from datakeel.ontology.functions import invoke_function
from datakeel.ontology.models import FunctionResult
from datakeel.ontology.production_functions import PRODUCTION_READ_MODELS
from datakeel.storage.image_geometry import upright_bytes
from datakeel.storage.workbench_assignees import assignees
from datakeel.storage.workbench_reads import (
    task_source,
    workbench_index,
    workbench_project,
    workbench_task,
)
from datakeel.storage.workbench_samples import dispatch_preview, task_samples, task_status

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


@router.get("/projects/{project_id}/task-samples")
def project_task_samples(
    project_id: str,
    query: Annotated[WorkbenchTaskSampleQuery, Query()],
    db: DatabaseDependency,
    request: Request,
) -> WorkbenchTaskSamples:
    """Name up to 500 tasks of the project by the file name recorded at import."""
    return task_samples(db, project_id, _caller(request), query)


@router.post("/projects/{project_id}/dispatch-preview")
def project_dispatch_preview(
    project_id: str,
    body: SkillDispatchPreviewRequest,
    db: DatabaseDependency,
    request: Request,
) -> SkillDispatchPreview:
    """Preview who a skill dispatch would assign each task to, and why others stay unassigned."""
    return dispatch_preview(db, project_id, _caller(request), body)


@router.get("/projects/{project_id}/assignees")
def project_assignees(
    project_id: str,
    db: DatabaseDependency,
    request: Request,
    stage: AssignmentStage = "annotation",
) -> WorkbenchAssignees:
    """List registered people who can take this stage's work, for assigning by name."""
    return assignees(db, project_id, _caller(request), stage)


@router.get("/tasks/{task_id}/status")
def task_status_view(task_id: str, db: DatabaseDependency, request: Request) -> WorkbenchTaskStatus:
    """Poll a task's state, assignments, effective lease deadlines and recent releases."""
    return task_status(db, task_id, _caller(request))


@router.get("/tasks/{task_id}/workbench")
def task_workbench(task_id: str, db: DatabaseDependency, request: Request) -> WorkbenchTask:
    """Read one sample with its complete revision, assignment and review evidence."""
    return workbench_task(db, task_id, _caller(request))


@router.get("/tasks/{task_id}/content", response_model=None)
def task_content(
    task_id: str, db: DatabaseDependency, request: Request, *, thumbnail: bool = False
) -> FileResponse | Response:
    """View a version-pinned source or a small image preview under the same source grants.

    Images are always shown upright: EXIF-oriented sources are re-encoded without the tag and
    with the EXIF Orientation already applied to the pixels (JPEG stays JPEG, others PNG;
    thumbnails are JPEG).
    """
    path, name = task_source(db, task_id, _caller(request))
    media_type = mimetypes.guess_type(name)[0]
    if thumbnail or (media_type is not None and media_type.startswith("image/")):
        # Revalidated on every view (grants are checked above), so a repeat costs one 304.
        stat = path.stat()
        tag = f'"upright-{int(thumbnail)}-{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        headers = {"ETag": tag, "Cache-Control": "private, no-cache"}
        if request.headers.get("if-none-match") == tag:
            return Response(status_code=304, headers=headers)
        upright = upright_bytes(path, thumbnail=1024 if thumbnail else None)
        if upright is not None:
            return Response(upright.content, media_type=upright.media_type, headers=headers)
    return FileResponse(path, media_type=media_type, filename=name)


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
