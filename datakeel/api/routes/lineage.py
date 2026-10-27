# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Lineage observations, bounded projections, and portable exports."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request

from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.models import JsonDocument, LineageEvent
from datakeel.lineage.models import GraphQuery, GraphView
from datakeel.storage import lineage_service as service
from datakeel.storage.views import View

router = APIRouter(prefix="/api", tags=["lineage"])


class EventRecorded(View):
    """Whether an idempotent append inserted a new observation."""

    inserted: bool


@router.post("/lineage/events")
def event(body: LineageEvent, db: DatabaseDependency) -> EventRecorded:
    """Append a lineage observation exactly once per idempotency key."""
    return EventRecorded(inserted=service.record_event(db, body))


@router.get("/lineage/graph", response_model_exclude_none=True)
def lineage(
    db: DatabaseDependency,
    query: Annotated[GraphQuery, Query()],
    request: Request,
) -> GraphView:
    """Read a depth-bounded asset lineage projection."""
    # Node names can quote source content, which passes the query-scope asset guard.
    return service.read_graph(
        db,
        query,
        access=AccessContext(
            actor=request.headers.get("X-Datakeel-Actor", "local-user"), entry="ask", scope="query"
        ),
    )


@router.get("/export")
def export(
    request: Request,
    db: DatabaseDependency,
    export_format: Annotated[Literal["openlineage", "croissant"], Query(alias="format")],
    dataset_id: str | None = None,
) -> JsonDocument | list[JsonDocument]:
    """Export observations or a selected dataset using a standard vocabulary."""
    access = AccessContext(
        actor=request.headers.get("X-Datakeel-Actor", "local-user"), entry="export", scope="export"
    )
    if export_format == "openlineage":
        return service.export_events(db, dataset_id, access=access)
    return service.export_dataset(db, dataset_id, str(request.base_url), access=access)
