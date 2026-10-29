# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read production facts; all mutations use the existing controlled action endpoints."""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import NotFoundError
from datakeel.core.models import JsonDocument
from datakeel.core.production_reads import (
    ProductionKind,
    ProductionObjectFilters,
    ProductionObjectQuery,
)
from datakeel.ontology.functions import invoke_function
from datakeel.ontology.models import FunctionResult
from datakeel.ontology.production_functions import PRODUCTION_READ_MODELS

router = APIRouter(prefix="/api/production", tags=["production"])


def _caller(request: Request) -> AccessContext:
    return AccessContext(
        actor=request.headers.get("X-Datakeel-Actor", "local"), entry="ask", scope="query"
    )


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
