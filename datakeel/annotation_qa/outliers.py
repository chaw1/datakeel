# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Robust category-conditioned size, aspect-ratio and span-length outliers.

Values are compared in log space within one category (box area relative to the
image when both image dimensions are declared). The modified z-score is
0.6745 * |x - median| / MAD (Iglewicz and Hoaglin, 1993). A value is an outlier
when it also differs from the median by a minimum factor (4x for box area, 3x for
box aspect ratio and span length) and either its score exceeds 3.5 or it lies
beyond the cohort's 1st-99th percentile range by more than that same factor. The
percentile fence catches extreme values in flat, wide cohorts where the MAD is
large. When another annotator of the same sample drew a matching item (box IoU at
the batch threshold or span Jaccard of at least 0.5) the panel corroborates its
geometry, so the score must exceed 5 instead. Cohorts need at least ten items;
when more than 10% of a cohort would be flagged, the cohort is treated as
multimodal and yields nothing.
"""

from collections import defaultdict
from collections.abc import Callable, Sequence
from math import log
from typing import NamedTuple

import numpy as np

from datakeel.annotation_qa.findings import box_is_valid, finding, span_is_valid
from datakeel.annotation_qa.geometry import box_iou
from datakeel.annotation_qa.grouping import sample_groups
from datakeel.core.annotation_models import (
    AnnotationBatch,
    AnnotationBox,
    AnnotationFinding,
    AnnotationRecord,
    AnnotationSpan,
    FindingCode,
)

_MIN_COHORT = 10
_MODIFIED_Z = 3.5
_CORROBORATED_Z = 5.0
_MAD_CONSISTENCY = 0.6745
_MAX_FLAGGED_SHARE = 0.1
_SPAN_MATCH = 0.5


class _Observation(NamedTuple):
    record: AnnotationRecord
    location: str
    value: float
    corroborated: bool


class _Rule(NamedTuple):
    code: FindingCode
    floor: float
    measure: str


_AREA = _Rule("bbox_size_outlier", log(4), "log box area")
_ASPECT = _Rule("bbox_aspect_outlier", log(3), "log box width/height")
_LENGTH = _Rule("span_length_outlier", log(3), "log span length")


def _span_overlap(left: AnnotationSpan, right: AnnotationSpan) -> float:
    overlap = min(left.end, right.end) - max(left.start, right.start)
    union = max(left.end, right.end) - min(left.start, right.start)
    return overlap / union if overlap > 0 and union > 0 else 0


def _corroborated[T](
    group: tuple[AnnotationRecord, ...],
    items: Callable[[AnnotationRecord], Sequence[T]],
    similar: Callable[[T, T], bool],
) -> dict[tuple[str, int], bool]:
    result: dict[tuple[str, int], bool] = {}
    for record in group:
        others = [item for other in group if other is not record for item in items(other)]
        for index, item in enumerate(items(record)):
            result[record.annotator_id, index] = any(similar(item, other) for other in others)
    return result


def _box_cohorts(
    batch: AnnotationBatch,
) -> dict[str, tuple[list[_Observation], list[_Observation]]]:
    groups: dict[str, tuple[list[_Observation], list[_Observation]]] = defaultdict(lambda: ([], []))

    def similar(left: AnnotationBox, right: AnnotationBox) -> bool:
        return box_iou(left, right) >= batch.iou_threshold

    for group in sample_groups(batch):
        support = _corroborated(group, lambda record: record.boxes or (), similar)
        for item in group:
            relative = item.image_width is not None and item.image_height is not None
            for index, box in enumerate(item.boxes or ()):
                if not box_is_valid(item, box):
                    continue
                width, height = box.x2 - box.x1, box.y2 - box.y1
                area = log(width) + log(height)
                if item.image_width is not None and item.image_height is not None:
                    area -= log(item.image_width) + log(item.image_height)
                kind = "relative" if relative else "absolute"
                areas, aspects = groups[f"{kind}:{box.category}"]
                matched = support[item.annotator_id, index]
                areas.append(_Observation(item, f"box[{index}]", area, matched))
                aspect = log(width) - log(height)
                aspects.append(_Observation(item, f"box[{index}]", aspect, matched))
    return groups


def _span_cohorts(batch: AnnotationBatch) -> dict[str, list[_Observation]]:
    groups: dict[str, list[_Observation]] = defaultdict(list)

    def similar(left: AnnotationSpan, right: AnnotationSpan) -> bool:
        return _span_overlap(left, right) >= _SPAN_MATCH

    for group in sample_groups(batch):
        support = _corroborated(group, lambda record: record.spans or (), similar)
        for item in group:
            for index, span in enumerate(item.spans or ()):
                if span_is_valid(item, span):
                    groups[span.category].append(
                        _Observation(
                            item,
                            f"span[{index}]",
                            log(span.end - span.start),
                            support[item.annotator_id, index],
                        )
                    )
    return groups


def _outliers(cohort: str, values: list[_Observation], rule: _Rule) -> list[AnnotationFinding]:
    if len(values) < _MIN_COHORT:
        return []
    array = np.array([item.value for item in values], dtype=np.float64)
    median = float(np.median(array))
    deviations = np.abs(array - median)
    mad = float(np.median(deviations))
    scale = _MAD_CONSISTENCY / mad if mad else float("inf")
    low, high = (float(value) for value in np.percentile(array, [1, 99]))
    fenced = (array > high + rule.floor) | (array < low - rule.floor)
    flagged = [
        index
        for index, deviation in enumerate(deviations)
        if deviation >= rule.floor
        and (
            bool(fenced[index])
            or deviation * scale > (_CORROBORATED_Z if values[index].corroborated else _MODIFIED_Z)
        )
    ]
    if len(flagged) > _MAX_FLAGGED_SHARE * len(values):
        return []
    return [
        finding(
            values[index].record,
            rule.code,
            "Value is a robust within-category outlier; check the annotation",
            (
                f"category={cohort}; {values[index].location}; cohort={len(values)}",
                f"{rule.measure}={array[index]:.4f}; median={median:.4f}; MAD={mad:.4f}",
                f"p1={low:.4f}; p99={high:.4f}; factor={np.exp(deviations[index]):.2f}x",
                f"floor={np.exp(rule.floor):.0f}x; corroborated={values[index].corroborated}",
            ),
            key=values[index].location,
        )
        for index in flagged
    ]


def box_outliers(batch: AnnotationBatch) -> tuple[AnnotationFinding, ...]:
    """Flag box area and aspect-ratio outliers within comparable category cohorts."""
    result: list[AnnotationFinding] = []
    for cohort, (areas, aspects) in sorted(_box_cohorts(batch).items()):
        result.extend(_outliers(cohort, areas, _AREA))
        result.extend(_outliers(cohort, aspects, _ASPECT))
    return tuple(result)


def span_outliers(batch: AnnotationBatch) -> tuple[AnnotationFinding, ...]:
    """Flag span lengths far from the usual length of the same span category."""
    result: list[AnnotationFinding] = []
    for cohort, lengths in sorted(_span_cohorts(batch).items()):
        result.extend(_outliers(cohort, lengths, _LENGTH))
    return tuple(result)
