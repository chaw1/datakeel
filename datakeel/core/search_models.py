# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded object discovery with only public identity and navigation context."""

from typing import Literal

from pydantic import Field

from datakeel.core.models import BoundaryModel

SearchKind = Literal[
    "dataset", "file", "version", "action_run", "table", "column", "metric", "term"
]
SEARCH_KINDS: tuple[SearchKind, ...] = (
    "dataset",
    "file",
    "version",
    "action_run",
    "table",
    "column",
    "metric",
    "term",
)


class SearchQuery(BoundaryModel):
    """Limit read-only discovery independently of the complete object inventory."""

    q: str = Field(default="", max_length=200)
    limit: int = Field(default=20, ge=1, le=100)


class SearchResult(BoundaryModel):
    """Expose stable object identity without private paths or connection metadata."""

    kind: SearchKind
    id: str
    name: str
    dataset_id: str | None = None
    version_id: str | None = None
    status: str | None = None
