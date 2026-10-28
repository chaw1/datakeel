# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen version comparison and published release boundary contracts."""

from typing import Literal

from pydantic import Field, JsonValue

from datakeel.core.models import BoundaryModel

DiffCategory = Literal["added", "removed", "content_changed", "metadata_changed", "unchanged"]


class ReleaseFile(BoundaryModel):
    """Portable release file facts without internal storage locations."""

    id: str
    filename: str
    sha256: str
    size: int = Field(ge=0)
    modality: str
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    source_version: str
    lineage_refs: tuple[str, ...]
    annotation_count: int = Field(ge=0)
    label_count: int = Field(ge=0)


class StoredReleaseFile(BoundaryModel):
    """Private typed storage boundary consumed only by local delivery services."""

    file: ReleaseFile
    object_key: str


class VersionSummary(BoundaryModel):
    """Observed annotations, mean file quality, and version-scoped review states."""

    annotation_count: int = 0
    label_count: int = 0
    quality_score: float = 0
    quality_basis: Literal["mean_file_quality"] = "mean_file_quality"
    evidence_decisions: dict[str, int] = Field(default_factory=dict)


class DiffFile(BoundaryModel):
    """One stable file identity compared across two immutable manifests."""

    category: DiffCategory
    file_id: str
    before: ReleaseFile | None = None
    after: ReleaseFile | None = None


class DiffCounts(BoundaryModel):
    """Complete five-way counts, independent of the requested page and filter."""

    added: int = 0
    removed: int = 0
    content_changed: int = 0
    metadata_changed: int = 0
    unchanged: int = 0


class VersionDiff(BoundaryModel):
    """A bounded page of comparisons with whole-version measurement summaries."""

    dataset_id: str
    before_version: str
    after_version: str
    counts: DiffCounts
    files: list[DiffFile]
    before_summary: VersionSummary
    after_summary: VersionSummary
    next_offset: int | None = None


class ReleaseView(BoundaryModel):
    """Immutable published manifest identity, provenance, and release notes."""

    id: str
    dataset_id: str
    version_id: str
    tag: str
    notes: str
    created_at: float
    manifest_sha256: str
    file_count: int
    total_bytes: int
    metadata: dict[str, JsonValue]
    summary: VersionSummary


class ReleaseFiles(BoundaryModel):
    """Bounded portable entries from an immutable published release."""

    files: list[ReleaseFile]
    next_offset: int | None = None


def _statistic(metadata: dict[str, JsonValue], count_key: str, keys: tuple[str, ...]) -> int:
    count = metadata.get(count_key)
    if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
        return count
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, list):
            return len(value)
        if value not in (None, "", {}, False):
            return 1
    return 0


def annotation_statistics(metadata: dict[str, JsonValue]) -> tuple[int, int]:
    """Count explicit totals or the registered annotation and label collections."""
    return (
        _statistic(metadata, "annotation_count", ("annotations", "annotation")),
        _statistic(metadata, "label_count", ("labels", "label")),
    )
