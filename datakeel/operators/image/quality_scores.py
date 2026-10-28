# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explain deterministic quality checks with independently configurable thresholds."""

from datakeel.core.models import Record
from datakeel.operators.base import ImageQualityParams
from datakeel.operators.image.quality_signals import ImageSignals

_STEEPNESS = 6


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


def _above(value: float, minimum: float) -> float:
    """Score 50 at the minimum, rising smoothly toward 100 above it and 0 below it."""
    if minimum <= 0:
        return 100.0
    ratio = (max(0.0, value) / minimum) ** _STEEPNESS
    return 100 * ratio / (1 + ratio)


def _below(value: float, maximum: float) -> float:
    return 100 / (1 + (value / maximum) ** 2)


def _exposure(signals: ImageSignals, params: ImageQualityParams) -> ImageQualityCheck:
    clipping = max(signals.dark_fraction, signals.bright_fraction)
    mean_score = 100 * min(signals.brightness, 255 - signals.brightness) / 127.5
    outside = not params.min_brightness <= signals.brightness <= params.max_brightness
    dim = signals.highlight < params.min_highlight
    # Highlights only lower the score once they fall below the minimum, so a
    # balanced image is graded by its mean and clipping alone.
    highlight_score = _above(signals.highlight, params.min_highlight) if dim else 100.0
    return _check(
        min(mean_score, 100 * (1 - clipping), highlight_score),
        failed=outside or dim or clipping > params.max_clipped_fraction,
        reason=(
            f"Mean luminance {signals.brightness:.3f}; allowed "
            f"[{params.min_brightness:g}, {params.max_brightness:g}]; "
            f"99.9th percentile {signals.highlight:.1f}; minimum {params.min_highlight:g}"
            f"{' (underexposed)' if dim else ''}; "
            f"dark/bright clipped fractions {signals.dark_fraction:.4f}/"
            f"{signals.bright_fraction:.4f}; maximum {params.max_clipped_fraction:g}; "
            f"{signals.bit_depth}-bit samples."
        ),
        code="brightness",
    )


def _blur(
    signals: ImageSignals, params: ImageQualityParams, blocked: str | None
) -> ImageQualityCheck:
    """Judge sharpness only when exposure and color variation leave edges to measure."""
    size = f"analysis size {signals.analysis_width}x{signals.analysis_height} px"
    if blocked is not None or signals.sharpness is None:
        cause = blocked or "no intensity variation"
        return _check(
            100, failed=False, reason=f"Sharpness not judged: {cause}; {size}.", code="blurry"
        )
    variance = signals.normalized_blur_variance
    legacy = params.blur_threshold
    score = _above(signals.sharpness, params.min_sharpness)
    if legacy:
        score = min(score, 100 * variance / (variance + legacy))
    return _check(
        score,
        failed=signals.sharpness < params.min_sharpness or variance < legacy,
        reason=(
            f"Edge sharpness {signals.sharpness:.3f}; minimum {params.min_sharpness:g}; "
            f"Laplacian variance {variance:.3f}; minimum {legacy:g}; {size}."
        ),
        code="blurry",
    )


def _noise(signals: ImageSignals, params: ImageQualityParams) -> ImageQualityCheck:
    impulses = signals.impulse_fraction
    return _check(
        min(
            _below(signals.noise_sigma, params.max_noise_sigma),
            _below(impulses, params.max_impulse_fraction),
        ),
        failed=(
            signals.noise_sigma > params.max_noise_sigma or impulses > params.max_impulse_fraction
        ),
        reason=(
            f"Robust native-pixel noise sigma {signals.noise_sigma:.3f}; "
            f"maximum {params.max_noise_sigma:g}; impulse pixel fraction {impulses:.4f}; "
            f"maximum {params.max_impulse_fraction:g}."
        ),
        code="noise",
    )


def evaluate(signals: ImageSignals, params: ImageQualityParams) -> ImageQualityChecks:
    """Score usability from sharpness, exposure, noise, dimensions and color variation.

    A failed exposure or a near-solid image is reported as that cause alone:
    dark, washed-out or flat pixels have weak edges, and calling them blurry
    as well would give the wrong reason.
    """
    minimum_side = min(signals.width, signals.height)
    exposure = _exposure(signals, params)
    solid_color = _check(
        100 * signals.color_stddev / (signals.color_stddev + params.min_color_stddev),
        failed=signals.color_stddev < params.min_color_stddev,
        reason=(
            f"Maximum channel standard deviation {signals.color_stddev:.3f}; "
            f"minimum {params.min_color_stddev:g}."
        ),
        code="solid_color",
    )
    blocked = "color variation failed" if solid_color.failed else None
    blocked = "exposure failed" if exposure.failed else blocked
    return ImageQualityChecks(
        blur=_blur(signals, params, blocked),
        exposure=exposure,
        noise=_noise(signals, params),
        resolution=_check(
            100 * minimum_side / params.min_resolution,
            failed=minimum_side < params.min_resolution,
            reason=f"Shortest side {minimum_side} px; minimum {params.min_resolution} px.",
            code="low_resolution",
        ),
        solid_color=solid_color,
    )
