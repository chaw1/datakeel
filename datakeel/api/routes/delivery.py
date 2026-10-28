# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Standalone release deliveries and archived six-category reconciliation endpoints."""

import tempfile
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.delivery_models import ReconcileReport
from datakeel.storage.delivery_service import (
    export_release,
    list_reconciliations,
    reconcile_release,
)

router = APIRouter(prefix="/api/releases", tags=["delivery"])


@router.post("/{release_id}/export", response_class=FileResponse)
def export(release_id: str, db: DatabaseDependency) -> FileResponse:
    """Download a verified portable tar containing the manifest and independent records."""
    temporary = tempfile.TemporaryDirectory(prefix="datakeel-download-")
    try:
        path = export_release(db, release_id, Path(temporary.name) / "delivery.tar.gz")
    except BaseException:
        temporary.cleanup()
        raise
    return FileResponse(
        path,
        media_type="application/gzip",
        filename=f"release-{release_id}.tar.gz",
        background=BackgroundTask(temporary.cleanup),
    )


@router.post("/{release_id}/reconcile")
def verify(release_id: str, db: DatabaseDependency) -> ReconcileReport:
    """Verify current stored bytes and archive the complete receipt."""
    return reconcile_release(db, release_id)


@router.get("/{release_id}/reconciliations")
def history(release_id: str, db: DatabaseDependency) -> list[ReconcileReport]:
    """Read prior six-category receipts including per-file differences."""
    return list_reconciliations(db, release_id)
