# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Unsupported keypoint metrics stay explicitly undefined instead of becoming perfect scores."""

from datakeel.annotation_qa import evaluate_annotations, prelabel_accuracy
from datakeel.annotation_qa.prelabel_match import comparable_records, compare_records
from datakeel.core.annotation_models import (
    AnnotationBatch,
    AnnotationKeypoint,
    AnnotationRecord,
    AnnotationSkeleton,
)


def _record(*, keypoints: bool) -> AnnotationRecord:
    return AnnotationRecord(
        sample_id="s",
        annotator_id="a",
        keypoints=(
            (
                AnnotationSkeleton(
                    category="person",
                    points=(AnnotationKeypoint(id="nose", x=1, y=2, state="visible"),),
                ),
            )
            if keypoints
            else None
        ),
    )


def test_keypoint_only_comparison_does_not_participate_in_iou_accuracy() -> None:
    """A one-sided native skeleton is not an empty detection result."""
    model, human = _record(keypoints=False), _record(keypoints=True)
    assert not comparable_records(model, human)
    comparison = compare_records(model, human)
    assert (comparison.model_count, comparison.human_count) == (0, 0)
    iou_50, iou_75, attributes = prelabel_accuracy([(model, human)])
    assert iou_50.all_hit_rate is None
    assert iou_75.f1 is None
    assert attributes.rate is None


def test_keypoint_agreement_is_explicitly_null_with_a_reason() -> None:
    """P26 exposes unsupported keypoint agreement without inventing a numeric value."""
    result = evaluate_annotations(AnnotationBatch(annotations=(_record(keypoints=True),)))
    assert result.keypoint_agreement is not None
    assert result.keypoint_agreement.value is None
    assert result.keypoint_agreement.reason == "Keypoint agreement is not supported"


def test_batches_without_keypoints_keep_the_old_result_shape() -> None:
    """The four existing components do not gain a new null metrics field."""
    result = evaluate_annotations(
        AnnotationBatch(annotations=(AnnotationRecord(sample_id="s", annotator_id="a", labels=()),))
    )
    assert "keypoint_agreement" not in result.model_dump(mode="json")
