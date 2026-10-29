# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Translate expected domain failures at the single HTTP error boundary."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from datakeel.core.errors import AuthorizationError, ConflictError, DatakeelError, NotFoundError
from datakeel.storage.production_revisions import RevisionConflictError


async def domain_error(_request: Request, exc: Exception) -> JSONResponse:
    """Map declared domain error categories to stable HTTP statuses."""
    status = 422
    if isinstance(exc, NotFoundError):
        status = 404
    elif isinstance(exc, ConflictError):
        status = 409
    elif isinstance(exc, AuthorizationError):
        status = 403
    if isinstance(exc, RevisionConflictError):
        return JSONResponse(
            status_code=status,
            content={
                "detail": str(exc),
                "latest_revision": exc.latest_revision.model_dump(mode="json")
                if exc.latest_revision
                else None,
            },
        )
    return JSONResponse(status_code=status, content={"detail": str(exc)})


def register_errors(app: FastAPI) -> None:
    """Install one shared mapping for domain and legacy validation failures."""
    app.add_exception_handler(DatakeelError, domain_error)
    app.add_exception_handler(ValueError, domain_error)
