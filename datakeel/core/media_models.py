# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen media measurements and time-bounded artifact provenance."""

from typing import Literal

from pydantic import Field, JsonValue, model_validator

from datakeel.core.media_alignment import MediaAlignment
from datakeel.core.models import Record


class MediaProbe(Record):
    """Describe decoded recording properties in milliseconds and display coordinates."""

    duration_ms: int = Field(ge=0)
    declared_duration_ms: int | None = Field(default=None, ge=0)
    format: str = ""
    codec: str = ""
    width: int = Field(default=0, ge=0)
    height: int = Field(default=0, ge=0)
    frame_rate: float = Field(default=0, ge=0, allow_inf_nan=False)
    rotation: int = 0
    audio_tracks: int = Field(default=0, ge=0)
    sample_rate: int = Field(default=0, ge=0)
    channels: int = Field(default=0, ge=0)


class MediaInterval(Record):
    """Locate a measured issue in the recording's local timeline."""

    code: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    severity: Literal["info", "warning", "critical"] = "warning"

    @model_validator(mode="after")
    def ordered_range(self) -> "MediaInterval":
        """Reject reversed source-time coordinates at the boundary."""
        if self.end_ms < self.start_ms:
            msg = "end_ms must not precede start_ms"
            raise ValueError(msg)
        return self


class MediaStep(Record):
    """Freeze one transformation and its immediate source time range."""

    operator: str
    version: str = "1.0.0"
    parameters: dict[str, JsonValue]
    parameters_digest: str
    source_file_id: str
    start_ms: int = Field(default=0, ge=0)
    end_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def ordered_range(self) -> "MediaStep":
        """Reject reversed transform coordinates before persistence."""
        if self.end_ms is not None and self.end_ms < self.start_ms:
            msg = "end_ms must not precede start_ms"
            raise ValueError(msg)
        return self


class MediaFileView(Record):
    """Expose typed recording measurements and source ranges to object pages."""

    probe: MediaProbe
    alignment: MediaAlignment | None = None
    issues: list[MediaInterval] = Field(default_factory=list[MediaInterval])
    history: list[MediaStep] = Field(default_factory=list[MediaStep])
    source_asset_id: str | None = None
    source_file_id: str | None = None
    source_start_ms: int = Field(default=0, ge=0)
    source_end_ms: int | None = Field(default=None, ge=0)
    metrics: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ordered_source_range(self) -> "MediaFileView":
        """Keep original-timeline ranges nonnegative and chronologically ordered."""
        if self.source_end_ms is not None and self.source_end_ms < self.source_start_ms:
            msg = "source_end_ms must not precede source_start_ms"
            raise ValueError(msg)
        return self


class MediaFileScore(Record):
    """Explain one recording or clip's measured signal deductions."""

    file_id: str
    filename: str
    duration_ms: int
    effective_duration_ms: int
    dimensions: dict[str, float]
    total: float
    reasons: list[str]


class MediaFailure(Record):
    """Name a recording that could not be processed, the operator and the reason."""

    file_id: str
    filename: str
    operator: str
    reason: str


class MediaSummary(Record):
    """Aggregate original recordings separately from their derived clips.

    Recordings that failed are listed in ``failures`` instead of being scored;
    ``partial`` is true when some recordings failed while others were processed.
    """

    original_duration_ms: int = 0
    effective_duration_ms: int = 0
    clip_count: int = 0
    duplicate_count: int = 0
    issue_distribution: dict[str, int] = Field(default_factory=dict)
    files: list[MediaFileScore] = Field(default_factory=list[MediaFileScore])
    failures: list[MediaFailure] = Field(default_factory=list[MediaFailure])
    partial: bool = False


class MediaArtifactRecord(Record):
    """Carry one published artifact's source and transformation chain to lineage."""

    file_id: str
    filename: str
    source_file_id: str
    source_asset_id: str
    start_ms: int
    end_ms: int | None
    history: list[MediaStep]
