# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Derive high/low confidence thresholds from reviewed model objects and assign task tiers.

Observations are (confidence, hit) for each model object of a draft that preceded an approved
human revision, where hit means an IoU >= 0.5 same-label match. A non-decreasing calibration
curve from confidence to hit rate is fitted by isotonic regression (pool adjacent violators):
neighbouring confidence groups whose rates would fall are merged into one flat segment. High is
the lowest confidence whose calibrated hit rate is at least 95%; low is the lowest confidence
whose calibrated hit rate is at least 50%, and objects below it are low. With fewer than 30
observations the defaults 0.85 and 0.5 apply and high drafts do not pass through to review.
"""

from collections.abc import Sequence

from datakeel.core.prelabel_models import (
    CalibrationSegment,
    ConfidenceThresholds,
    ConfidenceTier,
    TierRate,
)

DEFAULT_HIGH = 0.85
DEFAULT_LOW = 0.5
MINIMUM_OBJECTS = 30
HIGH_HIT_RATE = 0.95
LOW_HIT_RATE = 0.5
_ORDER: dict[ConfidenceTier, int] = {"low": 0, "medium": 1, "high": 2}


def object_tier(confidence: float, high: float | None, low: float | None) -> ConfidenceTier:
    """Place one confidence: high at or above ``high``, low below ``low``, else medium."""
    if high is not None and confidence >= high:
        return "high"
    if low is not None and confidence < low:
        return "low"
    return "medium"


def task_tier(
    confidences: Sequence[float], high: float | None, low: float | None
) -> ConfidenceTier:
    """Take the lowest object tier; a draft without objects is low."""
    if not confidences:
        return "low"
    return min((object_tier(value, high, low) for value in confidences), key=_ORDER.__getitem__)


def _rate(values: Sequence[tuple[float, bool]]) -> float | None:
    return sum(hit for _, hit in values) / len(values) if values else None


def calibration_curve(observations: Sequence[tuple[float, bool]]) -> tuple[CalibrationSegment, ...]:
    """Fit the isotonic confidence-to-hit-rate curve; each flat piece is one segment.

    Objects with equal confidence start as one block. Scanning upwards, a block whose rate is
    below the block before it is pooled with it (and further back while the order still breaks),
    which is the pool-adjacent-violators solution of the weighted least-squares fit.
    """
    blocks: list[list[float]] = []  # low, high, objects, hits
    for value in sorted({confidence for confidence, _ in observations}):
        inside = [hit for confidence, hit in observations if confidence == value]
        blocks.append([value, value, len(inside), sum(inside)])
        while len(blocks) > 1 and blocks[-2][3] * blocks[-1][2] > blocks[-1][3] * blocks[-2][2]:
            last = blocks.pop()
            blocks[-1][1:] = [last[1], blocks[-1][2] + last[2], blocks[-1][3] + last[3]]
    return tuple(
        CalibrationSegment(
            low=low, high=high, objects=int(objects), hits=int(hits), rate=hits / objects
        )
        for low, high, objects, hits in blocks
    )


def high_threshold(segments: Sequence[CalibrationSegment]) -> float | None:
    """Return the lowest confidence whose calibrated hit rate reaches 95%, if any does."""
    for segment in segments:
        if segment.rate >= HIGH_HIT_RATE:
            return segment.low
    return None


def low_threshold(segments: Sequence[CalibrationSegment]) -> float | None:
    """Return the lowest confidence whose calibrated hit rate reaches 50%, if any does."""
    for segment in segments:
        if segment.rate >= LOW_HIT_RATE:
            return segment.low
    return None


def tier_rates(
    observations: Sequence[tuple[float, bool]], high: float | None, low: float | None
) -> tuple[TierRate, ...]:
    """Measure the hit rate of reviewed objects inside each tier under these thresholds."""
    result: list[TierRate] = []
    for tier in ("high", "medium", "low"):
        inside = [item for item in observations if object_tier(item[0], high, low) == tier]
        hits = sum(hit for _, hit in inside)
        result.append(TierRate(tier=tier, objects=len(inside), hits=hits, rate=_rate(inside)))
    return tuple(result)


def calibrate(
    observations: Sequence[tuple[float, bool]],
    configured: tuple[float | None, float | None] = (None, None),
) -> ConfidenceThresholds:
    """Prefer project-configured thresholds, else reviewed evidence, else documented defaults."""
    notes: list[str] = []
    segments = calibration_curve(observations)
    measured = len(observations) >= MINIMUM_OBJECTS
    if not measured:
        high, low, source = DEFAULT_HIGH, DEFAULT_LOW, "default"
        notes.append("insufficient_samples")
    else:
        high, low, source = high_threshold(segments), low_threshold(segments), "calibrated"
        if high is None:
            notes.append("no_high_threshold")
        if low is None:
            # Nothing reaches a 50% hit rate: every object starts its person from empty.
            low = 1.0
            notes.append("no_low_threshold")
    if configured != (None, None):
        high = configured[0] if configured[0] is not None else high
        low = configured[1] if configured[1] is not None else low
        source = "configured"
    if high is not None and low > high:
        low = high
        notes.append("low_capped")
    return ConfidenceThresholds.model_validate(
        {
            "high": high,
            "low": low,
            "source": source,
            "objects": len(observations),
            "minimum_objects": MINIMUM_OBJECTS,
            "notes": tuple(notes),
            "tiers": tier_rates(observations, high, low),
            "segments": segments,
            "pass_through": measured or configured[0] is not None,
        }
    )
