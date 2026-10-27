# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Strict, immutable configuration for deterministic audio processing."""

from pydantic import Field

from datakeel.operators.base import Params


class ActivityParams(Params):
    """Estimate activity from short-time RMS, without a speech recognition model."""

    threshold_dbfs: float = Field(default=-40.0, ge=-100, le=0)
    frame_ms: int = Field(default=20, ge=5, le=100)
    min_activity_ms: int = Field(default=100, ge=0, le=10000)
    min_silence_ms: int = Field(default=100, ge=0, le=10000)


class TrimParams(ActivityParams):
    """Trim leading and trailing silence while preserving internal timing."""

    padding_ms: int = Field(default=20, ge=0, le=10000)


class LoudnessParams(Params):
    """Measure EBU R128 loudness and optionally create a normalized PCM artifact."""

    normalize: bool = False
    target_lufs: float = Field(default=-23.0, ge=-70, le=-5)
    loudness_tolerance_lu: float = Field(default=3.0, ge=0, le=30)
    true_peak_dbfs: float = Field(default=-1.0, ge=-9, le=0)
    loudness_range_lu: float = Field(default=7.0, ge=1, le=50)


class ClippingParams(Params):
    """Find full-scale plateaus and near-full-scale dwelling without downmixing channels."""

    threshold: float = Field(default=0.999, gt=0, le=1)
    min_consecutive_samples: int = Field(default=3, ge=1, le=10000)
    saturation_level: float = Field(default=0.85, gt=0, le=1)
    saturation_occupancy: float = Field(default=0.45, gt=0, le=1)
    window_ms: int = Field(default=20, ge=1, le=1000)
    merge_gap_ms: int = Field(default=50, ge=0, le=5000)


class DedupParams(Params):
    """Compare MFCC spectral shape and fluctuation time course within a duration tolerance.

    Varying sound is a copy when its MFCC fluctuations correlate within ``max_lag_ms``;
    steady tones are compared by spectral shape alone.
    """

    correlation_threshold: float = Field(default=0.6, ge=0, le=1)
    shape_threshold: float = Field(default=0.75, ge=0, le=1)
    stationary_threshold: float = Field(default=0.95, ge=0, le=1)
    max_lag_ms: int = Field(default=200, ge=0, le=5000)
    duration_tolerance: float = Field(default=0.05, ge=0, le=0.5)
    remove: bool = True
