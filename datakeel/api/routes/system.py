# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Health and bundled administrative application entry points."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from datakeel.storage.views import View

router = APIRouter(tags=["system"])
STATIC_DIRECTORY = Path(__file__).resolve().parents[2] / "web_dist"


class HealthView(View):
    """Service liveness indicator."""

    status: str = "ok"


@router.get("/api/health")
def health() -> HealthView:
    """Confirm that the HTTP application is serving requests."""
    return HealthView()


@router.get("/admin", include_in_schema=False)
def admin() -> FileResponse:
    """Serve the bundled administrative application."""
    return FileResponse(STATIC_DIRECTORY / "index.html")
