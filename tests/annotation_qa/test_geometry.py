# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Published geometric definitions and one-to-one entity matching boundaries."""

import pytest

from datakeel.annotation_qa.geometry import (
    box_agreement,
    box_iou,
    match_boxes,
    match_spans,
    span_agreement,
)
from datakeel.core.annotation_models import (
    AnnotationBatch,
    AnnotationBox,
    AnnotationRecord,
    AnnotationSpan,
)


def _box(x1: float, y1: float, x2: float, y2: float, category: str = "item") -> AnnotationBox:
    return AnnotationBox(category=category, x1=x1, y1=y1, x2=x2, y2=y2)


def _span(start: int, end: int, category: str = "item") -> AnnotationSpan:
    return AnnotationSpan(category=category, start=start, end=end)


def test_iou_paper_definition_known_rectangles() -> None:
    """Rezatofighi et al., CVPR 2019, Algorithm 1: I/(A+B-I).

    https://arxiv.org/abs/1902.09630, algorithm evaluated on integer rectangles:
    intersection=1, each area=4, union=7, IoU=1/7; identity=1, disjoint=0.
    """
    assert box_iou(_box(0, 0, 2, 2), _box(1, 1, 3, 3)) == pytest.approx(1 / 7)
    assert box_iou(_box(0, 0, 2, 2), _box(0, 0, 2, 2)) == 1
    assert box_iou(_box(0, 0, 2, 2), _box(3, 3, 4, 4)) == 0
    assert box_iou(_box(2, 2, 0, 0), _box(0, 0, 2, 2)) == 0


def test_box_matches_are_one_to_one_threshold_inclusive_and_category_independent() -> None:
    """Matching geometric boxes of different classes still records the class disagreement."""
    left = (_box(0, 0, 2, 2), _box(0, 0, 2, 2))
    right = (_box(0, 0, 1, 2, "other"),)
    assert match_boxes(left, right, 0.5) == ((0, 0, 0.5),)
    batch = AnnotationBatch(
        annotations=(
            AnnotationRecord(sample_id="s", annotator_id="a", boxes=left),
            AnnotationRecord(sample_id="s", annotator_id="b", boxes=right),
        )
    )
    result = box_agreement(batch)[0]
    assert result.match_rate == pytest.approx(2 / 3)
    assert result.mean_iou == 0.5
    assert result.category_agreement == 0


def test_span_published_evaluation_definition_known_counts() -> None:
    """Segura-Bedmar et al., SemEval 2013 Task 9, section 3.1, pp. 342-343.

    https://aclanthology.org/S13-2056.pdf defines exact boundary+type and
    type-with-overlap matching and micro F1. Applying those published definitions:
    gold=3, predicted=2, exact TP=1 gives .4, overlap TP=2 gives .8.
    """
    left = (_span(0, 4), _span(6, 10), _span(12, 16))
    right = (_span(0, 4), _span(7, 10))
    batch = AnnotationBatch(
        annotations=(
            AnnotationRecord(sample_id="s", annotator_id="a", spans=left),
            AnnotationRecord(sample_id="s", annotator_id="b", spans=right),
        )
    )
    result = span_agreement(batch)[0]
    assert result.exact_f1 == 0.4
    assert result.overlap_f1 == 0.8


def test_overlap_uses_maximum_matching_instead_of_greedy() -> None:
    """An augmenting path recovers two matches when the first overlapping choice blocks one."""
    assert match_spans((_span(0, 8), _span(0, 3)), (_span(0, 3), _span(5, 8)), overlap=True) == 2
    assert match_spans((_span(0, 3),), (_span(3, 8),), overlap=True) == 0
    assert match_spans((_span(0, 3),), (_span(0, 3, "other"),), overlap=True) == 0
    assert match_spans((_span(-1, 3),), (_span(-1, 3),)) == 0
    assert match_spans((_span(0, 3), _span(0, 3)), (_span(0, 3),)) == 1


def test_empty_and_missing_geometries_are_distinct() -> None:
    """Missing work does not count as no entities, and zero-total F1 is undefined."""
    missing = AnnotationBatch(
        annotations=(
            AnnotationRecord(sample_id="s", annotator_id="a"),
            AnnotationRecord(sample_id="s", annotator_id="b", boxes=(), spans=()),
        )
    )
    assert box_agreement(missing) == ()
    assert span_agreement(missing) == ()
    empty = missing.model_copy(
        update={
            "annotations": tuple(
                item.model_copy(update={"boxes": (), "spans": ()}) for item in missing.annotations
            )
        }
    )
    assert box_agreement(empty)[0].match_rate is None
    assert span_agreement(empty)[0].exact_f1 is None
    one = empty.model_copy(
        update={
            "annotations": (
                empty.annotations[0].model_copy(update={"spans": (_span(0, 3),)}),
                empty.annotations[1],
            )
        }
    )
    assert span_agreement(one)[0].exact_f1 == 0


def test_shared_invalid_boundaries_cannot_score_as_perfect_agreement() -> None:
    """Invalid annotations stay in the denominator even when both annotators repeat the error."""
    record = AnnotationRecord(
        sample_id="s",
        annotator_id="a",
        boxes=(_box(0, 0, 20, 20),),
        image_width=10,
        image_height=10,
        spans=(_span(0, 20),),
        text_length=10,
    )
    batch = AnnotationBatch(annotations=(record, record.model_copy(update={"annotator_id": "b"})))
    assert box_agreement(batch)[0].match_rate == 0
    assert span_agreement(batch)[0].exact_f1 == 0
    assert span_agreement(batch)[0].overlap_f1 == 0
    assert box_iou(_box(-1, -1, 2, 2), _box(-1, -1, 2, 2)) == 0
