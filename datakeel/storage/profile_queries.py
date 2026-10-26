# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read only published profile metadata, never source files or external connections."""

from typing import TYPE_CHECKING, cast

from pydantic import ValidationError as ModelValidationError
from sqlalchemy import select

from datakeel.core.models import FileItem
from datakeel.core.profile_models import ProfileDataset, ProfileGapEvidence, PublishedProfile
from datakeel.operators.table.models import TableProfile
from datakeel.operators.timeseries.models import GapsSummary
from datakeel.storage.database import Database, DatasetRow, VersionRow
from datakeel.storage.file_state import get_file_state, overlay_files

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _origin(session: "Session", dataset_id: str, file: FileItem) -> tuple[str, str] | None:
    identifier: object = file.metadata.get("original_source_file_id")
    if not isinstance(identifier, str):
        if "source_row_numbers" in file.metadata:
            return None
        identifier = file.id
    if get_file_state(session, dataset_id, identifier).deleted:
        return None
    versions = session.scalars(
        select(VersionRow)
        .where(VersionRow.dataset_id == dataset_id)
        .order_by(VersionRow.created_at, VersionRow.id)
    )
    for version in versions:
        if any(item.get("id") == identifier for item in version.manifest):
            return identifier, version.id
    return None


def _gap_evidence(
    dataset: ProfileDataset,
    file: FileItem,
    gaps: GapsSummary,
    origin: tuple[str, str],
) -> tuple[ProfileGapEvidence, ...]:
    time_column = next(
        (item.column for item in gaps.issues if item.rule == "sampling_gap"), "timestamp"
    )
    return tuple(
        ProfileGapEvidence(
            dataset_id=dataset.dataset_id,
            version_id=dataset.version_id,
            file_id=file.id,
            filename=file.filename,
            source_file_id=origin[0],
            source_version_id=origin[1],
            time_column=time_column,
            device=item.device,
            start_ms=item.start_ms,
            end_ms=item.end_ms,
            gap_ms=item.gap_ms,
            expected_interval_ms=item.expected_interval_ms,
            rows=item.rows,
        )
        for item in gaps.intervals
    )


def _profile(
    dataset: ProfileDataset,
    file: FileItem,
    origin: tuple[str, str] | None,
) -> PublishedProfile | None:
    raw_profile: object = file.metadata.get("table_profile")
    raw_series: object = file.metadata.get("timeseries")
    gaps_raw: object = (
        cast("dict[str, object]", raw_series).get("gaps") if isinstance(raw_series, dict) else None
    )
    if raw_profile is None and gaps_raw is None:
        return None
    base = PublishedProfile(
        dataset=dataset,
        file_id=file.id,
        filename=file.filename,
        has_gap_summary=gaps_raw is not None,
    )
    try:
        profile = TableProfile.model_validate(raw_profile) if raw_profile is not None else None
        gaps = GapsSummary.model_validate(gaps_raw) if gaps_raw is not None else None
        if origin is None and gaps is not None:
            return base.model_copy(update={"valid": False})
        evidence = _gap_evidence(dataset, file, gaps, origin) if gaps and origin else ()
        return base.model_copy(
            update={
                "columns": tuple(item.name for item in profile.columns) if profile else (),
                "gaps": evidence,
            }
        )
    except ModelValidationError:
        return base.model_copy(update={"valid": False})


def read_profiles(db: Database) -> tuple[PublishedProfile, ...]:
    """Return sanitized measurements from each dataset's latest immutable manifest."""
    result: list[PublishedProfile] = []
    with db.session() as session:
        for dataset in session.scalars(select(DatasetRow).order_by(DatasetRow.id)):
            version = session.scalar(
                select(VersionRow)
                .where(VersionRow.dataset_id == dataset.id)
                .order_by(VersionRow.created_at.desc(), VersionRow.id.desc())
                .limit(1)
            )
            if version is None:
                continue
            source = ProfileDataset(
                dataset_id=dataset.id,
                dataset_name=dataset.name,
                version_id=version.id,
            )
            files = overlay_files(
                session, dataset.id, [FileItem.model_validate(item) for item in version.manifest]
            )
            result.extend(
                profile
                for file in files
                if (profile := _profile(source, file, _origin(session, dataset.id, file)))
                is not None
            )
    return tuple(result)
