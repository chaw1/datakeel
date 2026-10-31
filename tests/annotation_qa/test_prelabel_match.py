# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""IoU object matching, polygon area and precision/recall/F1 for prelabel accuracy."""

import math
import random

import pytest

from datakeel.annotation_qa import prelabel_accuracy
from datakeel.annotation_qa.polygon_area import intersection_area, polygon_iou, signed_area
from datakeel.annotation_qa.prelabel_match import compare_records, record_objects, span_iou
from datakeel.core.annotation_models import (
    AnnotationBox,
    AnnotationPoint,
    AnnotationPolygon,
    AnnotationRecord,
    AnnotationSpan,
)


def _box(
    category: str, x1: float, y1: float, x2: float, y2: float, **attributes: str
) -> AnnotationBox:
    return AnnotationBox(category=category, x1=x1, y1=y1, x2=x2, y2=y2, attributes=dict(attributes))


def _record(**values: object) -> AnnotationRecord:
    return AnnotationRecord.model_validate({"sample_id": "s", "annotator_id": "a", **values})


def test_greedy_takes_highest_iou_pair_first_not_detection_order() -> None:
    # d0 overlaps g1 at 0.667 and g0 at 0.538; d1 overlaps g1 at 0.9 and g0 at 0.267.
    # Taking d0 first (detection order) would leave d1 without a hit; IoU order gives two.
    """Greedy takes highest iou pair first not detection order."""
    human = _record(boxes=[_box("cat", 5, 0, 15, 10), _box("cat", 0, 0, 10, 10)])
    model = _record(boxes=[_box("cat", 2, 0, 12, 10), _box("cat", 0, 0, 9, 10)])
    comparison = compare_records(model, human)
    assert [(pair.model_index, pair.human_index) for pair in comparison.pairs] == [(0, 0), (1, 1)]
    assert [round(pair.iou, 3) for pair in comparison.pairs] == [0.538, 0.9]
    assert comparison.hits() == 2
    assert comparison.all_hit()


def test_matches_only_within_the_same_label() -> None:
    """Matches only within the same label."""
    human = _record(boxes=[_box("cat", 0, 0, 10, 10)])
    model = _record(boxes=[_box("dog", 0, 0, 10, 10)])
    comparison = compare_records(model, human)
    assert comparison.pairs == ()
    assert comparison.model_hits() == (False,)


def test_strict_threshold_counts_only_pairs_at_or_above_075() -> None:
    """Strict threshold counts only pairs at or above 075."""
    human = _record(boxes=[_box("cat", 0, 0, 10, 10), _box("cat", 50, 50, 60, 60)])
    # IoU 0.8 and 0.6
    model = _record(boxes=[_box("cat", 0, 0, 10, 8), _box("cat", 50, 50, 60, 56)])
    comparison = compare_records(model, human)
    assert comparison.hits(0.5) == 2
    assert comparison.hits(0.75) == 1
    assert comparison.all_hit(0.5)
    assert not comparison.all_hit(0.75)
    assert comparison.model_hits(0.75) == (True, False)


def test_classification_matches_identical_label_sets_only() -> None:
    """Classification matches identical label sets only."""
    assert compare_records(_record(labels=["b", "a"]), _record(labels=["a", "b"])).hits() == 1
    different = compare_records(_record(labels=["a"]), _record(labels=["a", "b"]))
    assert (different.model_count, different.human_count, different.hits()) == (1, 1, 0)
    empty = compare_records(_record(labels=[]), _record(labels=[]))
    assert (empty.model_count, empty.human_count, empty.all_hit()) == (0, 0, True)


def test_spans_use_character_interval_iou() -> None:
    """Spans use character interval iou."""
    assert span_iou((0, 10), (5, 15)) == pytest.approx(5 / 15)
    assert span_iou((0, 10), (0, 10)) == 1
    assert span_iou((3, 3), (0, 10)) == 0
    model = _record(spans=[{"category": "name", "start": 0, "end": 10}])
    human = _record(spans=[AnnotationSpan(category="name", start=0, end=8)])
    assert compare_records(model, human).pairs[0].iou == pytest.approx(0.8)


def _square(x: float, y: float, size: float) -> tuple[tuple[float, float], ...]:
    return ((x, y), (x + size, y), (x + size, y + size), (x, y + size))


def test_polygon_area_iou_is_exact_for_convex_and_concave_shapes() -> None:
    """Polygon area iou is exact for convex and concave shapes."""
    assert polygon_iou(_square(0, 0, 2), _square(1, 1, 2)) == pytest.approx(1 / 7)
    letter_l = ((0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4))
    assert intersection_area(letter_l, _square(0, 0, 4)) == pytest.approx(7)
    assert intersection_area(tuple(reversed(letter_l)), _square(0, 0, 4)) == pytest.approx(7)
    # The concave notch of the L contains no area of the square placed inside it.
    assert intersection_area(letter_l, _square(2, 2, 1)) == pytest.approx(0)
    assert polygon_iou(((0, 0), (1, 1), (2, 2)), _square(0, 0, 2)) == 0


def _raster_iou(
    first: tuple[tuple[float, float], ...], second: tuple[tuple[float, float], ...]
) -> float:
    def inside(point: tuple[float, float], polygon: tuple[tuple[float, float], ...]) -> bool:
        result = False
        for (x1, y1), (x2, y2) in zip(polygon, (*polygon[1:], polygon[0]), strict=True):
            if (y1 > point[1]) != (y2 > point[1]) and point[0] < (x2 - x1) * (point[1] - y1) / (
                y2 - y1
            ) + x1:
                result = not result
        return result

    step = 0.05
    both = either = 0
    for row in range(200):
        for column in range(200):
            point = ((column + 0.5) * step, (row + 0.5) * step)
            left, right = inside(point, first), inside(point, second)
            both += left and right
            either += left or right
    return both / either if either else 0


def _star(center: tuple[float, float], generator: random.Random) -> tuple[tuple[float, float], ...]:
    points: list[tuple[float, float]] = []
    for index in range(7):
        angle = 2 * math.pi * index / 7
        radius = generator.uniform(1.0, 4.5)
        points.append((center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle)))
    return tuple(points)


def test_polygon_iou_agrees_with_independent_rasterization_on_random_star_shapes() -> None:
    """Polygon iou agrees with independent rasterization on random star shapes."""
    generator = random.Random(31)  # noqa: S311  # Reproducible geometry, not security.
    for _ in range(6):
        first = _star((5, 5), generator)
        second = _star((generator.uniform(4, 6), generator.uniform(4, 6)), generator)
        assert signed_area(first) > 0
        assert polygon_iou(first, second) == pytest.approx(_raster_iou(first, second), abs=0.01)


def test_polygon_objects_match_by_area_iou() -> None:
    """Polygon objects match by area iou."""

    def polygon(points: tuple[tuple[float, float], ...]) -> AnnotationPolygon:
        return AnnotationPolygon(
            category="roof", points=tuple(AnnotationPoint(x=x, y=y) for x, y in points)
        )

    model = _record(polygons=[polygon(_square(0, 0, 10))])
    human = _record(polygons=[polygon(_square(0, 0, 9))])
    assert compare_records(model, human).pairs[0].iou == pytest.approx(0.81)


def test_record_objects_follow_label_box_polygon_span_order() -> None:
    """Record objects follow label box polygon span order."""
    record = _record(
        labels=["x"],
        boxes=[_box("a", 0, 0, 1, 1)],
        spans=[AnnotationSpan(category="s", start=0, end=1)],
    )
    assert [(item.kind, item.position) for item in record_objects(record)] == [
        ("label_set", 0),
        ("box", 0),
        ("span", 0),
    ]


def test_accuracy_reports_precision_recall_f1_all_hit_and_attributes_separately() -> None:
    """Accuracy reports precision recall f1 all hit and attributes separately."""
    references = [
        (
            _record(boxes=[_box("cat", 0, 0, 10, 10, pose="sit"), _box("cat", 20, 20, 30, 30)]),
            _record(boxes=[_box("cat", 0, 0, 10, 10, pose="run")]),
        ),
        (_record(boxes=[_box("dog", 0, 0, 10, 8)]), _record(boxes=[_box("dog", 0, 0, 10, 10)])),
        (_record(boxes=[]), _record(boxes=[])),
    ]
    iou_50, iou_75, attributes = prelabel_accuracy(references)
    assert (iou_50.model_objects, iou_50.human_objects, iou_50.true_positives) == (3, 2, 2)
    assert iou_50.precision == pytest.approx(2 / 3)
    assert iou_50.recall == 1
    assert iou_50.f1 == pytest.approx(4 / 5)
    assert (iou_50.all_hit_tasks, iou_50.all_hit_rate) == (2, pytest.approx(2 / 3))
    assert (iou_75.true_positives, iou_75.all_hit_tasks) == (2, 2)
    # Attribute disagreement never removes a geometric hit.
    assert (attributes.matched_objects, attributes.consistent_objects) == (2, 1)
    assert attributes.rate == 0.5


def test_accuracy_is_null_without_objects() -> None:
    """Accuracy is null without objects."""
    iou_50, _, attributes = prelabel_accuracy([])
    assert (iou_50.precision, iou_50.recall, iou_50.f1, iou_50.all_hit_rate) == (
        None,
        None,
        None,
        None,
    )
    assert attributes.rate is None
