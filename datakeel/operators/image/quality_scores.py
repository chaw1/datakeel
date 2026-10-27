# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explain deterministic quality checks with independently configurable thresholds."""

from datakeel.core.models import Record
from datakeel.operators.base import ImageQualityParams
from datakeel.operators.image.quality_signals import ImageSignals


class ImageQualityCheck(Record):
    """Explain a bounded score and whether its measured signal crosses a threshold."""

    score: float
    failed: bool
    reason: str
    code: str


class ImageQualityChecks(Record):
    """Require all five checks in every quality measurement."""

    blur: ImageQualityCheck
    exposure: ImageQualityCheck
    noise: ImageQualityCheck
    resolution: ImageQualityCheck
    solid_color: ImageQualityCheck

    def values(self) -> tuple[ImageQualityCheck, ...]:
        """Return checks in their declared reporting order."""
        return (self.blur, self.exposure, self.noise, self.resolution, self.solid_color)


def _check(score: float, *, failed: bool, reason: str, code: str) -> ImageQualityCheck:
    return ImageQualityCheck(
        score=round(max(0.0, min(100.0, score)), 3),
        failed=failed,
        reason=reason,
        code=code,
    )


def _exposure(signals: ImageSignals, params: ImageQualityParams) -> ImageQualityCheck:
    clipping = max(signals.dark_fraction, signals.bright_fraction)
    mean_score = 100 * min(signals.brightness, 255 - signals.brightness) / 127.5
    outside = not params.min_brightness <= signals.brightness <= params.max_brightness
    return _check(
        min(mean_score, 100 * (1 - clipping)),
        failed=outside or clipping > params.max_clipped_fraction,
        reason=(
            f"Mean luminance {signals.brightness:.3f}; allowed "
            f"[{params.min_brightness:g}, {params.max_brightness:g}]; "
            f"dark/bright clipped fractions {signals.dark_fraction:.4f}/"
            f"{signals.bright_fraction:.4f}; maximum {params.max_clipped_fraction:g}."
        ),
        code="brightness",
    )


def evaluate(signals: ImageSignals, params: ImageQualityParams) -> ImageQualityChecks:
    """Score usability from sharpness, exposure, noise, dimensions and color variation."""
    blur = signals.normalized_blur_variance
    minimum_side = min(signals.width, signals.height)
    return ImageQualityChecks(
        blur=_check(
            100 * blur / (blur + params.blur_threshold) if params.blur_threshold else 100,
            failed=blur < params.blur_threshold,
            reason=(
                f"Normalized Laplacian variance {blur:.3f}; minimum {params.blur_threshold:g}; "
                f"analysis size {signals.analysis_width}x{signals.analysis_height} px."
            ),
            code="blurry",
        ),
        exposure=_exposure(signals, params),
        noise=_check(
            100 / (1 + (signals.noise_sigma / params.max_noise_sigma) ** 2),
            failed=signals.noise_sigma > params.max_noise_sigma,
            reason=(
                f"Robust native-pixel noise sigma {signals.noise_sigma:.3f}; "
                f"maximum {params.max_noise_sigma:g}."
            ),
            code="noise",
        ),
        resolution=_check(
            100 * minimum_side / params.min_resolution,
            failed=minimum_side < params.min_resolution,
            reason=f"Shortest side {minimum_side} px; minimum {params.min_resolution} px.",
            code="low_resolution",
        ),
        solid_color=_check(
            100 * signals.color_stddev / (signals.color_stddev + params.min_color_stddev),
            failed=signals.color_stddev < params.min_color_stddev,
            reason=(
                f"Maximum channel standard deviation {signals.color_stddev:.3f}; "
                f"minimum {params.min_color_stddev:g}."
            ),
            code="solid_color",
        ),
    )
