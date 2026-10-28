# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded merge comparison over authoritative immutable version manifests."""

from collections.abc import Iterator
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem, JsonDocument
from datakeel.core.release_models import (
    DiffCategory,
    DiffCounts,
    DiffFile,
    VersionDiff,
    VersionSummary,
    annotation_statistics,
)
from datakeel.storage.database import Database, DatasetRow
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.object_projection import content_digest, file_quality
from datakeel.storage.version_stream import (
    dataset_settings,
    portable_file,
    require_version,
    stream_manifest,
)

MAX_PAGE = 1000


@dataclass
class _Measurements:
    annotations: int = 0
    labels: int = 0
    quality: float = 0
    count: int = 0

    def observe(self, item: FileItem, dataset: DatasetRow) -> None:
        annotations, labels = annotation_statistics(portable_file(item, "").metadata)
        self.annotations += annotations
        self.labels += labels
        self.quality += file_quality(item, dataset)
        self.count += 1

    def summary(self, session: Session, version_id: str) -> VersionSummary:
        return VersionSummary(
            annotation_count=self.annotations,
            label_count=self.labels,
            quality_score=round(self.quality / self.count, 2) if self.count else 0,
            evidence_decisions=evidence_counts(session, version_id),
        )


def evidence_counts(session: Session, version_id: str) -> dict[str, int]:
    """Summarize active review states whose endpoints reference the exact version."""
    statement = (
        select(AssertionRow.status, func.count())
        .where(
            AssertionRow.active.is_(True),
            or_(
                AssertionRow.payload["subject"]["version"].as_string() == version_id,
                AssertionRow.payload["object"]["version"].as_string() == version_id,
            ),
        )
        .group_by(AssertionRow.status)
    )
    return dict(session.execute(statement).all())


def version_summary(session: Session, dataset: DatasetRow, version_id: str) -> VersionSummary:
    """Measure one immutable manifest with constant-size Python accumulation."""
    measured = _Measurements()
    for item in stream_manifest(session, version_id):
        measured.observe(item, dataset)
    return measured.summary(session, version_id)


def _pairs(
    before: Iterator[FileItem], after: Iterator[FileItem]
) -> Iterator[tuple[FileItem | None, FileItem | None]]:
    left, right = next(before, None), next(after, None)
    while left is not None or right is not None:
        if right is None or (left is not None and left.id < right.id):
            yield left, None
            left = next(before, None)
        elif left is None or right.id < left.id:
            yield None, right
            right = next(after, None)
        else:
            yield left, right
            left, right = next(before, None), next(after, None)


def _category(before: FileItem | None, after: FileItem | None) -> DiffCategory:
    if before is None:
        return "added"
    if after is None:
        return "removed"
    if before.sha256 != after.sha256:
        return "content_changed"
    return (
        "unchanged" if _metadata_digest(before) == _metadata_digest(after) else "metadata_changed"
    )


def _metadata_digest(item: FileItem) -> str:
    metadata = JsonDocument.model_validate(item.metadata).root
    return content_digest(
        {
            "filename": item.filename,
            "size": item.size,
            "modality": item.modality,
            "metadata": {key: value for key, value in metadata.items() if key != "object_key"},
        }
    )


def _compare(
    session: Session,
    dataset: DatasetRow,
    versions: tuple[str, str],
    page: tuple[int, int],
    category: DiffCategory | None,
) -> VersionDiff:
    before_id, after_id = versions
    counts = dict.fromkeys(DiffCounts.model_fields, 0)
    measurements = (_Measurements(), _Measurements())
    files: list[DiffFile] = []
    matching = 0
    for left, right in _pairs(
        stream_manifest(session, before_id), stream_manifest(session, after_id)
    ):
        kind = _category(left, right)
        counts[kind] += 1
        for item, measured in zip((left, right), measurements, strict=True):
            if item is not None:
                measured.observe(item, dataset)
        if category is None or category == kind:
            if page[0] <= matching < sum(page):
                files.append(
                    DiffFile(
                        category=kind,
                        file_id=left.id
                        if left is not None
                        else right.id
                        if right is not None
                        else "",
                        before=portable_file(left, before_id) if left else None,
                        after=portable_file(right, after_id) if right else None,
                    )
                )
            matching += 1
    return VersionDiff(
        dataset_id=dataset.id,
        before_version=before_id,
        after_version=after_id,
        counts=DiffCounts.model_validate(counts),
        files=files,
        before_summary=measurements[0].summary(session, before_id),
        after_summary=measurements[1].summary(session, after_id),
        next_offset=sum(page) if matching > sum(page) else None,
    )


def compare_versions(
    db: Database,
    dataset_id: str,
    before: str,
    after: str,
    page: tuple[int, int] = (0, 100),
    category: DiffCategory | None = None,
) -> VersionDiff:
    """Compare exact same-dataset snapshots; output memory is bounded by page size."""
    if page[0] < 0 or not 1 <= page[1] <= MAX_PAGE:
        message = "Diff offset must be nonnegative and limit must be between 1 and 1000"
        raise ValidationError(message)
    with db.session() as session:
        require_version(session, dataset_id, before)
        require_version(session, dataset_id, after)
        return _compare(
            session, dataset_settings(session, dataset_id), (before, after), page, category
        )
