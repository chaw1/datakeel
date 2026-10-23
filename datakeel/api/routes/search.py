# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-only global object discovery for keyboard navigation."""

from typing import Annotated

from fastapi import APIRouter, Query

from datakeel.api.dependencies import DatabaseDependency
from datakeel.core.search_models import SearchQuery, SearchResult
from datakeel.storage.search import search_objects

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def search(query: Annotated[SearchQuery, Query()], db: DatabaseDependency) -> list[SearchResult]:
    """Return public identities with sufficient context to navigate to their object pages."""
    return search_objects(db, query)
