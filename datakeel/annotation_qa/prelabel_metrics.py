# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Aggregate one-to-one object matches into precision, recall, F1 and all-hit task rates.

Precision is true positives over model objects, recall is true positives over human objects
and F1 is 2TP / (2TP + FP + FN). Each is null when its denominator is zero. A task is all-hit
when every model object and every human object is matched at the threshold, so two empty
records agree.
"""

from collections.abc import Sequence

from datakeel.annotation_qa.prelabel_match import (
    HIT_IOU,
    STRICT_IOU,
    RecordComparison,
    compare_records,
)
from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.prelabel_models import AttributeAgreement, IoUAccuracy


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def iou_accuracy(comparisons: Sequence[RecordComparison], threshold: float) -> IoUAccuracy:
    """Summarize micro-averaged object counts at one IoU threshold."""
    model = sum(item.model_count for item in comparisons)
    human = sum(item.human_count for item in comparisons)
    hits = sum(item.hits(threshold) for item in comparisons)
    all_hit = sum(item.all_hit(threshold) for item in comparisons)
    return IoUAccuracy(
        threshold=threshold,
        model_objects=model,
        human_objects=human,
        true_positives=hits,
        precision=_ratio(hits, model),
        recall=_ratio(hits, human),
        f1=_ratio(2 * hits, model + human),
        all_hit_tasks=all_hit,
        all_hit_rate=_ratio(all_hit, len(comparisons)),
    )


def attribute_agreement(comparisons: Sequence[RecordComparison]) -> AttributeAgreement:
    """Count identical attributes only among IoU >= 0.5 matches, never affecting hits."""
    pairs = [pair for item in comparisons for pair in item.pairs if pair.iou >= HIT_IOU]
    consistent = sum(pair.attributes_equal for pair in pairs)
    return AttributeAgreement(
        matched_objects=len(pairs),
        consistent_objects=consistent,
        rate=_ratio(consistent, len(pairs)),
    )


def prelabel_accuracy(
    references: Sequence[tuple[AnnotationRecord, AnnotationRecord]],
) -> tuple[IoUAccuracy, IoUAccuracy, AttributeAgreement]:
    """Compare (model draft, human reference) pairs at IoU 0.5 and 0.75."""
    comparisons = [compare_records(model, human) for model, human in references]
    return (
        iou_accuracy(comparisons, HIT_IOU),
        iou_accuracy(comparisons, STRICT_IOU),
        attribute_agreement(comparisons),
    )
