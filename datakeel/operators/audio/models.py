# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen audio measurements exchanged between audio operators."""

from pydantic import Field

from datakeel.core.media_models import MediaInterval
from datakeel.core.models import Record


class AudioMetrics(Record):
    """Carry measured audio facts while keeping activity-estimation limits explicit."""

    vad_method: str | None = None
    vad_intervals: tuple[MediaInterval, ...] | None = None
    silence_intervals: tuple[MediaInterval, ...] | None = None
    active_ratio: float | None = None
    silence_ratio: float | None = None
    integrated_lufs: float | None = None
    loudness_range_lu: float | None = None
    true_peak_dbfs: float | None = None
    target_lufs: float | None = None
    loudness_deviation_lu: float | None = None
    loudness_measurable: bool | None = None
    clipping_ratio: float | None = None
    clipped_samples: int | None = None
    fingerprint: tuple[float, ...] | None = None
    fingerprint_method: str | None = None
    duplicate_of: str | None = None


class ActivityResult(Record):
    """Describe detected activity and silence in the source file's time coordinates."""

    duration_ms: int = Field(ge=0)
    active: tuple[MediaInterval, ...]
    silent: tuple[MediaInterval, ...]


class LoudnessMeasurement(Record):
    """Represent finite EBU R128 measurements, or unmeasurable digital silence."""

    integrated_lufs: float | None
    loudness_range_lu: float | None
    true_peak_dbfs: float | None
    threshold_lufs: float | None


class Fingerprint(Record):
    """Keep a fixed-size temporal MFCC signature with source duration."""

    duration_ms: int
    coefficients: tuple[float, ...]
