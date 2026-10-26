# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measured source quality with conservative, deterministic multi-source aggregation."""

from datetime import UTC, datetime
from itertools import groupby

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.data_asset_models import QualityPoint
from datakeel.core.models import AssetRef, FileItem
from datakeel.quality.scoring import score_quality
from datakeel.storage.data_asset_targets import resolve_access_targets
from datakeel.storage.database import DatasetRow, VersionRow
from datakeel.storage.datasets import latest_files


def _dataset_quality(
    session: Session,
    dataset: DatasetRow,
    version_id: str | None,
) -> tuple[float | None, tuple[QualityPoint, ...]]:
    statement = select(VersionRow).where(VersionRow.dataset_id == dataset.id)
    if version_id is not None:
        statement = statement.where(VersionRow.id == version_id)
    versions = session.scalars(statement.order_by(VersionRow.created_at, VersionRow.id))
    points = tuple(
        QualityPoint(
            occurred_at=datetime.fromtimestamp(row.created_at, UTC),
            score=score_quality(
                [FileItem.model_validate(item) for item in row.manifest], dataset.quality_config
            ).total,
        )
        for row in versions
        if row.manifest
    )
    if version_id is not None:
        return (points[-1].score if points else None), points
    files = latest_files(session, dataset)
    return (score_quality(files, dataset.quality_config).total if files else None), points


def _combined_trend(sources: list[tuple[QualityPoint, ...]]) -> tuple[QualityPoint, ...]:
    observations = sorted(
        (
            (point.occurred_at, index, point.score)
            for index, points in enumerate(sources)
            for point in points
        )
    )
    observed: dict[int, float] = {}
    result: list[QualityPoint] = []
    measured_sources = sum(bool(points) for points in sources)
    for moment, group in groupby(observations, key=lambda item: item[0]):
        observed.update({index: score for _time, index, score in group})
        if len(observed) == measured_sources:
            result.append(QualityPoint(occurred_at=moment, score=min(observed.values())))
    return tuple(result)


def asset_quality(
    session: Session,
    target: AssetRef,
) -> tuple[float | None, tuple[QualityPoint, ...]]:
    """Use exact dataset snapshots; other resources take the lowest measured source score.

    A trend begins when all sources with quality evidence have been observed and
    updates at each source-version timestamp. Unknown sources stay unknown rather
    than acquiring invented measurements. No file contents or remote sources are read.
    """
    refs = (
        (target,) if target.asset_type == "dataset" else resolve_access_targets(session, (target,))
    )
    sources: list[tuple[QualityPoint, ...]] = []
    scores: list[float] = []
    for ref in refs:
        if ref.asset_type != "dataset":
            continue
        dataset = session.get(DatasetRow, ref.asset_id)
        if dataset is None:
            continue
        score, points = _dataset_quality(session, dataset, ref.version)
        sources.append(points)
        if score is not None:
            scores.append(score)
    return (min(scores) if scores else None), _combined_trend(sources)
