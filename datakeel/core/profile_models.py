# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen profile answers backed by published manifests and original source intervals."""

from typing import Literal, Self

from pydantic import Field, model_validator

from datakeel.core.models import AssetRef, BoundaryModel

GapSort = Literal["gap_count", "total_gap_ms"]


class ProfileDataset(BoundaryModel):
    """Pin a dataset candidate to its current immutable published version."""

    dataset_id: str = Field(min_length=1)
    dataset_name: str = Field(min_length=1)
    version_id: str = Field(min_length=1)


class ProfileGapEvidence(BoundaryModel):
    """Bind one sampling-axis gap to a file version, bounding rows and UTC interval."""

    dataset_id: str = Field(min_length=1)
    version_id: str = Field(min_length=1)
    file_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    source_file_id: str = Field(min_length=1)
    source_version_id: str = Field(min_length=1)
    row_coordinates: Literal["original_source"] = "original_source"
    time_column: str = Field(min_length=1)
    device: str = Field(min_length=1)
    start_ms: int
    end_ms: int
    gap_ms: int = Field(gt=0)
    expected_interval_ms: int = Field(gt=0)
    rows: tuple[int, int]

    @model_validator(mode="after")
    def bounded_interval(self) -> Self:
        """Reject invented durations or missing source coordinates."""
        if any(row < 1 for row in self.rows) or self.rows[0] == self.rows[1]:
            msg = "Gap evidence requires two distinct positive source rows"
            raise ValueError(msg)
        if self.gap_ms != self.end_ms - self.start_ms - self.expected_interval_ms:
            msg = "Missing duration must equal the observed interval minus expected sampling"
            raise ValueError(msg)
        return self


class DeviceGapRank(BoundaryModel):
    """Expose only aggregates reproduced exactly by the attached source intervals."""

    device: str = Field(min_length=1)
    interval_count: int = Field(gt=0)
    total_gap_ms: int = Field(gt=0)
    evidence: tuple[ProfileGapEvidence, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def measured_totals(self) -> Self:
        """Require complete evidence for every published count and duration."""
        if self.interval_count != len(self.evidence) or self.total_gap_ms != sum(
            item.gap_ms for item in self.evidence
        ):
            msg = "Device gap totals must agree with the attached interval evidence"
            raise ValueError(msg)
        if any(item.device != self.device for item in self.evidence):
            msg = "Gap evidence must belong to the ranked device"
            raise ValueError(msg)
        identities = {
            (item.source_file_id, item.source_version_id, item.start_ms, item.end_ms, item.rows)
            for item in self.evidence
        }
        if len(identities) != len(self.evidence):
            msg = "Gap evidence must not be counted twice"
            raise ValueError(msg)
        return self


class ProfileAnswer(BoundaryModel):
    """Keep sampling-axis measurements distinct from per-column missing-value claims."""

    intent: Literal["device_gaps"] = "device_gaps"
    scope: Literal["sampling_time_axis"] = "sampling_time_axis"
    sort_by: GapSort = "gap_count"
    requested_column: str | None = None
    dataset: ProfileDataset | None = None
    ranking: tuple[DeviceGapRank, ...] = ()
    candidates: tuple[ProfileDataset, ...] = ()
    reason_code: (
        Literal[
            "no_profile",
            "ambiguous_dataset",
            "unknown_subject",
            "unknown_column",
            "incomplete_profile",
            "no_recorded_gaps",
        ]
        | None
    ) = None


class PublishedProfile(BoundaryModel):
    """Transfer a sanitized current-manifest measurement out of the storage layer."""

    dataset: ProfileDataset
    file_id: str
    filename: str
    columns: tuple[str, ...] = ()
    gaps: tuple[ProfileGapEvidence, ...] = ()
    has_gap_summary: bool = False
    valid: bool = True


def profile_citations(profile: ProfileAnswer | None) -> tuple[AssetRef, ...]:
    """Cite immutable file and dataset versions without re-reading source content."""
    if profile is None or profile.dataset is None or not profile.ranking:
        return ()
    dataset = profile.dataset
    references = [
        AssetRef(asset_id=dataset.dataset_id, version=dataset.version_id),
        AssetRef(asset_type="version", asset_id=dataset.version_id, version=dataset.version_id),
    ]
    files = {
        (item.source_file_id, item.source_version_id): item
        for rank in profile.ranking
        for item in rank.evidence
    }
    references.extend(
        AssetRef(
            asset_type="file",
            asset_id=item.source_file_id,
            version=item.source_version_id,
            display_name=item.filename,
        )
        for _, item in sorted(files.items())
    )
    return tuple(references)
