# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Paged immutable version comparison and approved publication read APIs."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.models import BoundaryModel
from datakeel.core.release_models import DiffCategory, ReleaseFiles, ReleaseView, VersionDiff
from datakeel.storage.release_service import get_release, list_release_files, list_releases
from datakeel.storage.version_diff import compare_versions

router = APIRouter(prefix="/api", tags=["releases"])


class DiffQuery(BoundaryModel):
    """Bounded query parameters for same-dataset version comparison."""

    before: str
    after: str
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)
    category: DiffCategory | None = None


@router.get("/datasets/{identifier}/diff")
def version_diff(
    identifier: str,
    query: Annotated[DiffQuery, Depends()],
    db: DatabaseDependency,
) -> VersionDiff:
    """Compare any two same-dataset versions by stable file identity, hash, and metadata."""
    return compare_versions(
        db, identifier, query.before, query.after, (query.offset, query.limit), query.category
    )


@router.get("/datasets/{identifier}/releases")
def releases(identifier: str, db: DatabaseDependency) -> list[ReleaseView]:
    """List approved immutable publications without exposing object locations."""
    return list_releases(db, identifier)


@router.get("/releases/{release_id}")
def release(release_id: str, db: DatabaseDependency) -> ReleaseView:
    """Read the exact metadata and measurements frozen at publication."""
    return get_release(db, release_id)


@router.get("/releases/{release_id}/files")
def release_files(
    release_id: str,
    db: DatabaseDependency,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> ReleaseFiles:
    """Page through frozen release entries independently of mutable source settings."""
    return list_release_files(db, release_id, offset, limit)
