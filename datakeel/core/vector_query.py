# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-only, bounded vector evidence and snapshot pagination contracts."""

from typing import Literal

from pydantic import Field

from datakeel.core.evidence_models import Assertion, AssertionStatus
from datakeel.core.models import AssetRef, BoundaryModel
from datakeel.core.vector_models import Digest
from datakeel.core.vector_results import VectorTaskReport

VectorKind = Literal["duplicate", "cluster", "outlier", "coverage"]
VECTOR_PREDICATES: dict[VectorKind, str] = {
    "duplicate": "semantic_duplicate_of",
    "cluster": "semantic_cluster_member",
    "outlier": "semantic_outlier",
    "coverage": "coverage_gap",
}


class VectorQuery(BoundaryModel):
    """Bind every page to an explicit task run and exact typed filters."""

    run_id: str = Field(min_length=1, max_length=200)
    dataset_id: str | None = Field(default=None, min_length=1)
    kind: VectorKind = "duplicate"
    reference_id: str | None = Field(default=None, min_length=1)
    cluster_id: str | None = Field(default=None, min_length=1)
    subject_ids: tuple[str, ...] = Field(default=(), max_length=5000)
    statuses: tuple[AssertionStatus, ...] = Field(
        default=("candidate", "accepted"), min_length=1, max_length=3
    )
    page_size: int = Field(default=20, ge=1, le=200)
    cursor: str | None = Field(default=None, min_length=1, max_length=2048)


class VectorQueryEvent(BoundaryModel):
    """Expose source closure and contract provenance without raw execution parameters."""

    event_id: str
    operator: str
    mode: str
    implementation: str
    contract: str
    inputs: tuple[AssetRef, ...]


class VectorQueryResult(BoundaryModel):
    """Distinguish stale or unpublished evidence from a successful empty result."""

    run_id: str
    kind: VectorKind
    snapshot: Digest
    reference_digest: Digest
    status: Literal["current", "stale", "unpublished"]
    reason: str | None = None
    items: tuple[Assertion, ...]
    total: int = Field(ge=0)
    next_cursor: str | None
    report: VectorTaskReport
    events: tuple[VectorQueryEvent, ...]
