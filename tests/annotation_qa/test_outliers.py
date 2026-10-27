# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Robust size, aspect-ratio and span-length outliers."""

from math import exp

import numpy as np

from datakeel.annotation_qa.outliers import box_outliers, span_outliers
from datakeel.core.annotation_models import (
    AnnotationBatch,
    AnnotationBox,
    AnnotationRecord,
    AnnotationSpan,
)


def _record(sample: str, width: float, height: float, annotator: str = "a") -> AnnotationRecord:
    return AnnotationRecord(
        sample_id=sample,
        annotator_id=annotator,
        boxes=(AnnotationBox(category="car", x1=0, y1=0, x2=width, y2=height),),
    )


def _codes(records: list[AnnotationRecord]) -> list[tuple[str, str]]:
    findings = box_outliers(AnnotationBatch(annotations=tuple(records)))
    return sorted((item.sample_id, item.code) for item in findings)


def test_tight_cohort_uses_minimum_factors() -> None:
    """With almost no spread, only a 4x area or 3x aspect deviation is reported."""
    cohort = [_record(f"s{index}", 50 + index % 3, 50 - index % 2) for index in range(20)]
    assert _codes(cohort) == []
    assert _codes([*cohort, _record("big", 105, 105)]) == [("big", "bbox_size_outlier")]
    assert _codes([*cohort, _record("thin", 120, 30)]) == [("thin", "bbox_aspect_outlier")]
    assert _codes([*cohort, _record("ok", 80, 80)]) == []


def test_small_cohorts_and_multimodal_cohorts_are_not_judged() -> None:
    """Ten items are required, and a mode holding over 10% of a cohort is not an outlier."""
    assert _codes([*(_record(f"s{i}", 50, 50) for i in range(8)), _record("x", 500, 500)]) == []
    small = [_record(f"s{i}", 50, 50) for i in range(16)]
    large = [_record(f"l{i}", 400, 400) for i in range(4)]
    assert _codes(small + large) == []


def test_corroborated_box_needs_stronger_evidence() -> None:
    """A box matched by another annotator needs modified z above 5 instead of 3.5."""
    rng = np.random.default_rng(7)
    cohort = [
        _record(f"s{index}", exp(rng.normal(4, 0.3)), exp(rng.normal(4, 0.3)))
        for index in range(200)
    ]
    areas = np.log([(box.x2 * box.y2) for item in cohort for box in item.boxes or ()])
    median = float(np.median(areas))
    mad = float(np.median(np.abs(areas - median)))
    side = exp((median + 4.25 * mad / 0.6745) / 2)
    alone = _codes([*cohort, _record("x", side, side)])
    together = _codes([*cohort, _record("x", side, side), _record("x", side, side, "b")])
    assert alone == [("x", "bbox_size_outlier")]
    assert together == []


def test_percentile_fence_catches_extremes_in_flat_cohorts() -> None:
    """In a flat 100x size range the MAD is wide; 4x beyond the 99th percentile still counts."""
    sides = np.linspace(20, 200, 300)
    cohort = [_record(f"s{index}", side, side) for index, side in enumerate(sides)]
    huge = [_record("huge", 1000, 1000, annotator) for annotator in ("a", "b", "c")]
    assert {code for _, code in _codes([*cohort, *huge])} == {"bbox_size_outlier"}
    assert {sample for sample, _ in _codes([*cohort, *huge])} == {"huge"}


def test_invalid_boxes_are_left_to_bounds_rules() -> None:
    """Out-of-image boxes are reported as invalid, not as statistical outliers."""
    cohort = [_record(f"s{index}", 50, 50) for index in range(20)]
    outside = _record("out", 500, 500).model_copy(update={"image_width": 100, "image_height": 100})
    assert _codes([*cohort, outside]) == []


def test_span_length_outlier_within_category() -> None:
    """An entity ten times longer than its category's usual length is reported."""
    records = [
        AnnotationRecord(
            sample_id=f"s{index}",
            annotator_id="a",
            spans=(AnnotationSpan(category="PER", start=0, end=5 + index % 3),),
        )
        for index in range(20)
    ]
    records.append(
        AnnotationRecord(
            sample_id="long",
            annotator_id="a",
            spans=(AnnotationSpan(category="PER", start=0, end=60),),
        )
    )
    findings = span_outliers(AnnotationBatch(annotations=tuple(records)))
    assert [(item.sample_id, item.code) for item in findings] == [("long", "span_length_outlier")]
