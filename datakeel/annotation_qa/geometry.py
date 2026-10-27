# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One-to-one geometric agreement for boxes and half-open text spans."""

from itertools import product
from typing import TYPE_CHECKING

import numpy as np

from datakeel.annotation_qa.grouping import paired_records
from datakeel.core.annotation_models import (
    AnnotationBatch,
    AnnotationBox,
    AnnotationRecord,
    AnnotationSpan,
    BoxAgreement,
    SpanAgreement,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def box_iou(a: AnnotationBox, b: AnnotationBox) -> float:
    """Compute intersection over union; zero-area or reversed boxes never match."""
    widths = np.array([a.x2 - a.x1, b.x2 - b.x1], dtype=np.float64)
    heights = np.array([a.y2 - a.y1, b.y2 - b.y1], dtype=np.float64)
    if min(a.x1, a.y1, b.x1, b.y1) < 0 or bool(np.any(widths <= 0) | np.any(heights <= 0)):
        return 0
    intersection = max(0, min(a.x2, b.x2) - max(a.x1, b.x1)) * max(
        0, min(a.y2, b.y2) - max(a.y1, b.y1)
    )
    union = float(np.sum(widths * heights)) - intersection
    return float(intersection / union) if union > 0 and np.isfinite(union) else 0


def match_boxes(
    left: tuple[AnnotationBox, ...], right: tuple[AnnotationBox, ...], threshold: float
) -> tuple[tuple[int, int, float], ...]:
    """Greedily choose descending IoU with index tie breaks, independent of category.

    This is deterministic greedy matching, not Hungarian maximum assignment.
    Category agreement is measured separately on these geometric matches.
    """
    candidates = sorted(
        ((box_iou(a, b), i, j) for (i, a), (j, b) in product(enumerate(left), enumerate(right))),
        key=lambda item: (-item[0], item[1], item[2]),
    )
    used_left: set[int] = set()
    used_right: set[int] = set()
    matches: list[tuple[int, int, float]] = []
    for score, i, j in candidates:
        if score >= threshold and i not in used_left and j not in used_right:
            matches.append((i, j, score))
            used_left.add(i)
            used_right.add(j)
    return tuple(matches)


def _bounded_boxes(record: AnnotationRecord) -> tuple[AnnotationBox, ...]:
    result: list[AnnotationBox] = []
    for box in record.boxes or ():
        outside = (record.image_width is not None and box.x2 > record.image_width) or (
            record.image_height is not None and box.y2 > record.image_height
        )
        result.append(box.model_copy(update={"x2": box.x1}) if outside else box)
    return tuple(result)


def _bounded_spans(record: AnnotationRecord) -> tuple[AnnotationSpan, ...]:
    return tuple(
        span.model_copy(update={"end": span.start})
        if record.text_length is not None and span.end > record.text_length
        else span
        for span in record.spans or ()
    )


def box_agreement(batch: AnnotationBatch) -> tuple[BoxAgreement, ...]:
    """Aggregate shared samples; match rate is 2*matches/(left_count+right_count)."""
    result: list[BoxAgreement] = []
    for a, b, records in paired_records(batch):
        shared = [
            (_bounded_boxes(x), _bounded_boxes(y))
            for x, y in records
            if x.boxes is not None and y.boxes is not None
        ]
        if not shared:
            continue
        count_a, count_b = sum(len(x) for x, _ in shared), sum(len(y) for _, y in shared)
        scores: list[float] = []
        category_matches = 0
        for left, right in shared:
            matches = match_boxes(left, right, batch.iou_threshold)
            scores.extend(score for _, _, score in matches)
            category_matches += sum(left[i].category == right[j].category for i, j, _ in matches)
        matched = len(scores)
        result.append(
            BoxAgreement(
                annotator_a=a,
                annotator_b=b,
                sample_count=len(shared),
                box_count_a=count_a,
                box_count_b=count_b,
                matched_count=matched,
                match_rate=2 * matched / (count_a + count_b) if count_a + count_b else None,
                mean_iou=float(np.mean(scores)) if scores else None,
                category_agreement=category_matches / matched if matched else None,
            )
        )
    return tuple(result)


def _valid_span(span: AnnotationSpan) -> bool:
    return 0 <= span.start < span.end


def _overlaps(a: AnnotationSpan, b: AnnotationSpan) -> bool:
    return a.category == b.category and min(a.end, b.end) > max(a.start, b.start)


def _exact(a: AnnotationSpan, b: AnnotationSpan) -> bool:
    return a == b


def _augment(
    index: int, edges: list[list[int]], matched: dict[int, int], visited: set[int]
) -> bool:
    for target in edges[index]:
        if target in visited:
            continue
        visited.add(target)
        if target not in matched or _augment(matched[target], edges, matched, visited):
            matched[target] = index
            return True
    return False


def match_spans(
    left: tuple[AnnotationSpan, ...], right: tuple[AnnotationSpan, ...], *, overlap: bool = False
) -> int:
    """Find maximum-cardinality same-category matching using augmenting paths.

    Overlap requires positive intersection of half-open coordinates. Invalid spans
    are counted as annotations, but cannot produce exact or overlapping matches.
    """
    predicate: Callable[[AnnotationSpan, AnnotationSpan], bool] = _overlaps if overlap else _exact
    edges = [
        [j for j, b in enumerate(right) if _valid_span(a) and _valid_span(b) and predicate(a, b)]
        for a in left
    ]
    matched: dict[int, int] = {}
    for i in range(len(left)):
        _augment(i, edges, matched, set())
    return len(matched)


def span_agreement(batch: AnnotationBatch) -> tuple[SpanAgreement, ...]:
    """Micro-average exact/overlap F1 across shared samples, with empty pairs undefined."""
    result: list[SpanAgreement] = []
    for a, b, records in paired_records(batch):
        shared = [
            (_bounded_spans(x), _bounded_spans(y))
            for x, y in records
            if x.spans is not None and y.spans is not None
        ]
        if not shared:
            continue
        count_a, count_b = sum(len(x) for x, _ in shared), sum(len(y) for _, y in shared)
        exact = sum(match_spans(x, y) for x, y in shared)
        overlap = sum(match_spans(x, y, overlap=True) for x, y in shared)
        total = count_a + count_b
        result.append(
            SpanAgreement(
                annotator_a=a,
                annotator_b=b,
                sample_count=len(shared),
                span_count_a=count_a,
                span_count_b=count_b,
                exact_matches=exact,
                overlap_matches=overlap,
                exact_f1=float(np.divide(2 * exact, total)) if total else None,
                overlap_f1=float(np.divide(2 * overlap, total)) if total else None,
            )
        )
    return tuple(result)
