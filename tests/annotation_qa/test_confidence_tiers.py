# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Confidence calibration, tiers, mirrored cross-check agreement and noisy-OR risk."""

import pytest

from datakeel.annotation_qa.confidence_tiers import (
    calibrate,
    calibration_curve,
    high_threshold,
    low_threshold,
    object_tier,
    task_tier,
)
from datakeel.annotation_qa.prelabel_crosscheck import agreements, object_confidence, tuple_iou
from datakeel.annotation_qa.risk_scoring import (
    HIGH_RISK,
    RULE_WEIGHTS,
    disagreement_reason,
    finding_objects,
    finding_reason,
    noisy_or,
    risk_score,
    sample_draw,
)
from datakeel.core.annotation_models import AnnotationFinding


def _known_rates() -> list[tuple[float, bool]]:
    """Fifty objects whose hit rates per confidence band are known by construction."""
    rows: list[tuple[float, bool]] = []
    rows += [(0.95, True)] * 10
    rows += [(0.9, True)] * 19 + [(0.9, False)]
    rows += [(0.7, True)] * 5 + [(0.7, False)] * 5
    rows += [(0.3, True)] * 2 + [(0.3, False)] * 8
    return rows


def test_known_hit_rates_give_the_documented_thresholds() -> None:
    """High is the lowest confidence calibrated to >=95% hits, low the lowest to >=50%."""
    rows = _known_rates()
    segments = calibration_curve(rows)
    # Already non-decreasing: 0.3 -> 20%, 0.7 -> exactly 50%, 0.9 -> exactly 95%, 0.95 -> 100%.
    assert [(item.low, item.objects, item.hits) for item in segments] == [
        (0.3, 10, 2),
        (0.7, 10, 5),
        (0.9, 20, 19),
        (0.95, 10, 10),
    ]
    assert high_threshold(segments) == pytest.approx(0.9)
    assert low_threshold(segments) == pytest.approx(0.7)
    result = calibrate(rows)
    assert (result.high, result.low, result.source) == (0.9, 0.7, "calibrated")
    assert result.objects == 50
    assert result.pass_through is True
    assert len(result.segments) == 4
    rates = {tier.tier: tier for tier in result.tiers}
    assert (rates["high"].objects, rates["high"].hits) == (30, 29)
    assert (rates["medium"].objects, rates["medium"].hits) == (10, 5)
    assert (rates["low"].objects, rates["low"].hits) == (10, 2)


def test_violating_neighbours_are_pooled_into_one_flat_segment() -> None:
    """A band that hits less often than the band below it is merged so the curve never falls."""
    rows = [(0.4, False)] * 10 + [(0.6, True)] * 8 + [(0.6, False)] * 2
    rows += [(0.7, True)] * 6 + [(0.7, False)] * 4 + [(0.9, True)] * 10
    segments = calibration_curve(rows)
    assert [(item.low, item.high, item.objects, item.hits) for item in segments] == [
        (0.4, 0.4, 10, 0),
        (0.6, 0.7, 20, 14),
        (0.9, 0.9, 10, 10),
    ]
    assert segments[1].rate == pytest.approx(0.7)
    # The 80%-accurate 0.6 band stays medium instead of being sent to an empty start.
    assert calibrate(rows).low == pytest.approx(0.6)


def test_a_configured_high_below_the_measured_low_caps_low_and_is_noted() -> None:
    """The calibrated curve keeps low <= high; only a configured high can force the cap."""
    rows = [(0.5, False)] * 5 + [(0.6, False)] * 2 + [(0.99, True)] * 100
    assert (calibrate(rows).high, calibrate(rows).low) == (0.99, 0.99)
    result = calibrate(rows, (0.9, None))
    assert (result.high, result.low) == (0.9, 0.9)
    assert result.notes == ("low_capped",)


def test_insufficient_samples_fall_back_to_defaults_with_reason() -> None:
    """Fewer than 30 reviewed objects use 0.85 and 0.5, say why, and do not pass through."""
    result = calibrate([(0.9, True)] * 29)
    assert (result.high, result.low, result.source) == (0.85, 0.5, "default")
    assert result.notes == ("insufficient_samples",)
    assert result.objects == 29
    assert result.pass_through is False
    assert calibrate([(0.9, True)] * 30).pass_through is True
    assert calibrate([(0.9, True)] * 29, (0.9, None)).pass_through is True


def test_configured_thresholds_override_per_field() -> None:
    """A project may pin one or both thresholds; the other stays measured or default."""
    result = calibrate(_known_rates(), (0.97, None))
    assert (result.high, result.low, result.source) == (0.97, 0.7, "configured")


def test_missing_thresholds_are_noted() -> None:
    """All-miss evidence has no high bar and starts every object empty; all-hit has no low."""
    misses = [(0.5, False)] * 15 + [(0.6, False)] * 15
    result = calibrate(misses)
    assert result.notes == ("no_high_threshold", "no_low_threshold")
    assert (result.high, result.low) == (None, 1.0)
    hits = calibrate([(0.5, True)] * 30)
    assert (hits.high, hits.low, hits.notes) == (0.5, 0.5, ())


def test_task_tier_is_the_lowest_object_and_empty_is_low() -> None:
    """One weak object pulls the task down; no objects means start low."""
    assert object_tier(0.85, 0.85, 0.5) == "high"
    assert object_tier(0.5, 0.85, 0.5) == "medium"
    assert object_tier(0.49, 0.85, 0.5) == "low"
    assert task_tier([0.9, 0.95], 0.85, 0.5) == "high"
    assert task_tier([0.9, 0.6], 0.85, 0.5) == "medium"
    assert task_tier([0.9, 0.2, 0.6], 0.85, 0.5) == "low"
    assert task_tier([], 0.85, 0.5) == "low"
    assert task_tier([0.99], None, None) == "medium"


def test_mirrored_agreement_matches_one_to_one_by_label() -> None:
    """Each mirrored box confirms at most one primary box of the same label."""
    primary = [("cat", (0, 0, 10, 10)), ("cat", (1, 0, 11, 10)), ("dog", (50, 50, 60, 60))]
    mirrored = [("cat", (0, 0, 10, 10)), ("dog", (100, 100, 110, 110))]
    assert agreements(primary, mirrored) == (1.0, 0.0, 0.0)
    assert tuple_iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(50 / 150)
    assert object_confidence(0.8, 0.6, "combined") == pytest.approx(0.7)
    assert object_confidence(None, 0.6, "combined") == pytest.approx(0.55)
    assert object_confidence(0.8, 0.6, "cross_check") == pytest.approx(0.6)
    assert object_confidence(0.8, None, "combined") == pytest.approx(0.8)
    assert object_confidence(None, None, "self") == pytest.approx(0.5)


def _finding(code: str, evidence: tuple[str, ...] = ()) -> AnnotationFinding:
    return AnnotationFinding.model_construct(
        finding_id="f",
        code=code,
        sample_id="s",
        annotator_id="a",
        reason=f"{code} reason",
        evidence=evidence,
    )


def test_noisy_or_risk_is_monotone_and_strong_rules_are_high_alone() -> None:
    """Adding a hit never lowers risk; every rule except rare_category is high risk alone."""
    assert noisy_or([]) == 0
    assert noisy_or([0.5, 0.5]) == pytest.approx(0.75)
    assert noisy_or([0.5, 0.5, 0.2]) > noisy_or([0.5, 0.5])
    assert all(
        weight >= HIGH_RISK for code, weight in RULE_WEIGHTS.items() if code != "rare_category"
    )
    assert RULE_WEIGHTS["rare_category"] < HIGH_RISK
    reasons = [finding_reason(_finding("bbox_size_outlier", ("box[2] area=4",)))]
    assert reasons[0].objects[0].model_dump() == {"kind": "box", "index": 2}
    assert risk_score(reasons) == pytest.approx(0.5)
    label = finding_objects(_finding("minority_label"))
    assert label[0].model_dump() == {"kind": "label_set", "index": 0}
    assert finding_reason(_finding("unlisted_rule")).weight == pytest.approx(0.3)


def test_disagreement_weight_scales_with_confidence_and_difference() -> None:
    """Departing from a confident draft is a reason; agreeing or a zero draft is not."""
    reason = disagreement_reason(0.9, 1.0, ())
    assert reason is not None
    assert reason.weight == pytest.approx(0.45)
    assert disagreement_reason(0.9, 0.0, ()) is None
    assert disagreement_reason(0.0, 1.0, ()) is None


def test_sampling_draw_is_reproducible_and_uniform_enough() -> None:
    """The same submission always draws the same value; draws spread over [0, 1)."""
    assert sample_draw("t", 0, "r") == sample_draw("t", 0, "r")
    assert sample_draw("t", 1, "r") != sample_draw("t", 0, "r")
    draws = [sample_draw(f"task-{index}", 0, "rev") for index in range(2000)]
    assert all(0 <= value < 1 for value in draws)
    assert 0.45 < sum(value < 0.5 for value in draws) / len(draws) < 0.55
