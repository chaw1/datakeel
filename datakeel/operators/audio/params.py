# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Strict, immutable configuration for deterministic audio processing."""

from pydantic import Field, model_validator

from datakeel.core.errors import ValidationError
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
    """Measure EBU R128 loudness and optionally create a normalized PCM artifact.

    Integrated loudness inside ``[acceptable_min_lufs, acceptable_max_lufs]``, widened
    by ``loudness_tolerance_lu`` on both sides, is not flagged. The default range runs
    from the EBU R128 broadcast target (-23 LUFS) to the -14 LUFS normalization level
    of the loudest common streaming platforms, with R128's +/-1 LU tolerance; set the
    range to -23..-23 for strict broadcast delivery (-23 +/- 1). ``target_lufs`` is the
    level that ``normalize`` produces.
    """

    normalize: bool = False
    target_lufs: float = Field(default=-23.0, ge=-70, le=-5)
    acceptable_min_lufs: float = Field(default=-23.0, ge=-70, le=-5)
    acceptable_max_lufs: float = Field(default=-14.0, ge=-70, le=-5)
    loudness_tolerance_lu: float = Field(default=1.0, ge=0, le=30)
    true_peak_dbfs: float = Field(default=-1.0, ge=-9, le=0)
    loudness_range_lu: float = Field(default=7.0, ge=1, le=50)

    @model_validator(mode="after")
    def ordered_range(self) -> "LoudnessParams":
        """Reject an acceptable range whose lower bound exceeds its upper bound."""
        if self.acceptable_min_lufs > self.acceptable_max_lufs:
            msg = "acceptable_min_lufs must not exceed acceptable_max_lufs"
            raise ValidationError(msg)
        return self


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
