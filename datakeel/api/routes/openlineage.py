# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Fail-closed bearer authentication for external OpenLineage event producers."""

from hmac import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.errors import AuthorizationError
from datakeel.core.orchestration import OpenLineageReceipt, OpenLineageRunEvent
from datakeel.core.settings import Settings, get_settings
from datakeel.storage.openlineage_store import ingest_openlineage

router = APIRouter(prefix="/api/openlineage", tags=["openlineage"])
_bearer = HTTPBearer(auto_error=False)


def authenticated_settings(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Settings:
    """Require an explicitly configured nonempty ingestion token before any writes."""
    settings = get_settings()
    token = settings.openlineage_token
    expected = token.get_secret_value() if token else ""
    if (
        not expected
        or credentials is None
        or not compare_digest(credentials.credentials.encode(), expected.encode())
    ):
        msg = "OpenLineage ingestion requires a configured bearer credential"
        raise AuthorizationError(msg)
    return settings


@router.post("/events")
def ingest(
    body: OpenLineageRunEvent,
    db: DatabaseDependency,
    settings: Annotated[Settings, Depends(authenticated_settings)],
) -> OpenLineageReceipt:
    """Record one standard run transition and enrich its mapped catalog objects."""
    return ingest_openlineage(db, body, settings.openlineage_namespaces)
