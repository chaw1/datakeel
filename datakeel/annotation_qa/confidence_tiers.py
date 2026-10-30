# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Derive high/low confidence thresholds from reviewed model objects and assign task tiers.

Observations are (confidence, hit) for each model object of a draft that preceded an approved
human revision, where hit means an IoU >= 0.5 same-label match. Candidate thresholds are the
confidence values that occur. High is the lowest candidate t whose objects with confidence >= t
hit at least 95% of the time; low is the highest candidate t whose objects with confidence < t
hit less than 50% of the time, capped at high. With fewer than 30 observations the defaults
0.85 and 0.5 apply.
"""

from collections.abc import Sequence

from datakeel.core.prelabel_models import ConfidenceThresholds, ConfidenceTier, TierRate

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


def high_threshold(observations: Sequence[tuple[float, bool]]) -> float | None:
    """Return the lowest occurring t with hit rate >= 95% among confidence >= t, if any."""
    for candidate in sorted({value for value, _ in observations}):
        rate = _rate([item for item in observations if item[0] >= candidate])
        if rate is not None and rate >= HIGH_HIT_RATE:
            return candidate
    return None


def low_threshold(observations: Sequence[tuple[float, bool]]) -> float | None:
    """Return the highest occurring t with hit rate < 50% among confidence < t, if any."""
    for candidate in sorted({value for value, _ in observations}, reverse=True):
        rate = _rate([item for item in observations if item[0] < candidate])
        if rate is not None and rate < LOW_HIT_RATE:
            return candidate
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
    if len(observations) < MINIMUM_OBJECTS:
        high, low, source = DEFAULT_HIGH, DEFAULT_LOW, "default"
        notes.append("insufficient_samples")
    else:
        high, low, source = high_threshold(observations), low_threshold(observations), "calibrated"
        if high is None:
            notes.append("no_high_threshold")
        if low is None:
            notes.append("no_low_threshold")
        if high is not None and low is not None and low > high:
            low = high
            notes.append("low_capped")
    if configured != (None, None):
        high = configured[0] if configured[0] is not None else high
        low = configured[1] if configured[1] is not None else low
        source = "configured"
    return ConfidenceThresholds.model_validate(
        {
            "high": high,
            "low": low,
            "source": source,
            "objects": len(observations),
            "minimum_objects": MINIMUM_OBJECTS,
            "notes": tuple(notes),
            "tiers": tier_rates(observations, high, low),
        }
    )
