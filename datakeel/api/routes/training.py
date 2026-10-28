# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable training splits, read-only previews and cross-split leakage evidence."""

from fastapi import APIRouter, Request

from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.annotation_sampling import AnnotationQualityReport
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import NotFoundError
from datakeel.core.models import AssetRef
from datakeel.core.training_export_models import TrainingAnnotationImport
from datakeel.core.training_models import LeakageReport, SplitComparison, SplitRequest, SplitSet
from datakeel.storage.data_asset_access import require_access
from datakeel.storage.training_import import import_training_annotations
from datakeel.storage.training_store import (
    check_leakage,
    compare_splits,
    create_split,
    get_split,
    list_splits,
    preview_leakage,
    preview_split,
)

router = APIRouter(
    prefix="/api/datasets/{identifier}/versions/{version_id}/training", tags=["training"]
)


def _access(request: Request) -> AccessContext:
    return AccessContext(
        actor=request.headers.get("X-Datakeel-Actor", "local"), entry="ask", scope="query"
    )


def _split(
    db: DatabaseDependency, identifier: str, version_id: str, split_id: str, request: Request
) -> SplitSet:
    value = get_split(db, identifier, split_id, access=_access(request))
    if value.version_id != version_id:
        message = "Split set not found in the requested version"
        raise NotFoundError(message)
    return value


@router.get("/splits")
def splits(
    identifier: str, version_id: str, db: DatabaseDependency, request: Request
) -> tuple[SplitSet, ...]:
    """List the named immutable split sets saved on this exact source version."""
    return list_splits(db, identifier, version_id, access=_access(request))


@router.post("/splits", status_code=201)
def generate_split(
    identifier: str, version_id: str, body: SplitRequest, db: DatabaseDependency, request: Request
) -> SplitSet:
    """Generate or import directory assignments and persist a named immutable split set."""
    return create_split(db, identifier, version_id, body, access=_access(request))


@router.post("/preview")
def preview(
    identifier: str, version_id: str, body: SplitRequest, db: DatabaseDependency, request: Request
) -> SplitSet:
    """Calculate seeded class distributions without creating a saved split set."""
    return preview_split(db, identifier, version_id, body, access=_access(request))


@router.post("/leakage")
def preview_report(
    identifier: str, version_id: str, body: SplitRequest, db: DatabaseDependency, request: Request
) -> LeakageReport:
    """Inspect external directory splits without persisting their assignments."""
    return preview_leakage(db, identifier, version_id, body, access=_access(request))


@router.get("/splits/{split_id}")
def split_detail(
    identifier: str, version_id: str, split_id: str, db: DatabaseDependency, request: Request
) -> SplitSet:
    """Read saved assignments, configuration and per-class distributions."""
    return _split(db, identifier, version_id, split_id, request)


@router.get("/splits/{split_id}/leakage")
def leakage(
    identifier: str, version_id: str, split_id: str, db: DatabaseDependency, request: Request
) -> LeakageReport:
    """Return direct cross-split sample pairs, signal types and Hamming distances."""
    _split(db, identifier, version_id, split_id, request)
    return check_leakage(db, identifier, split_id, access=_access(request))


@router.get("/compare")
def comparison(
    identifier: str,
    version_id: str,
    left: str,
    right: str,
    db: DatabaseDependency,
    request: Request,
) -> SplitComparison:
    """Compare two split sets from this same version, including changed sample assignments."""
    _split(db, identifier, version_id, left, request)
    _split(db, identifier, version_id, right, request)
    return compare_splits(db, identifier, left, right, access=_access(request))


@router.post("/import-annotations", status_code=201)
def import_annotations(
    identifier: str,
    version_id: str,
    body: TrainingAnnotationImport,
    db: DatabaseDependency,
    request: Request,
) -> AnnotationQualityReport:
    """Import typed COCO or YOLO detection annotations through the existing review store."""
    require_access(
        db,
        (AssetRef(asset_id=identifier, version=version_id),),
        _access(request),
    )
    return import_training_annotations(db, identifier, version_id, body, access=_access(request))
