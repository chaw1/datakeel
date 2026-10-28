# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Conservative review candidates with stable identities and explicit evidence."""

import hashlib
import json
from collections import Counter
from itertools import combinations

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

_DUPLICATE_IOU = 0.9


def finding(
    record: AnnotationRecord,
    code: FindingCode,
    reason: str,
    evidence: tuple[str, ...],
    key: str = "",
    related: tuple[str, ...] = (),
) -> AnnotationFinding:
    """Build a deterministic finding identity independent of mutable explanatory text."""
    identity = json.dumps([record.sample_id, record.annotator_id, code, key])
    return AnnotationFinding(
        finding_id=hashlib.sha256(identity.encode()).hexdigest()[:24],
        sample_id=record.sample_id,
        annotator_id=record.annotator_id,
        code=code,
        reason=reason,
        evidence=evidence,
        related_sample_ids=related,
    )


def minority_findings(batch: AnnotationBatch) -> tuple[AnnotationFinding, ...]:
    """Flag a minority label set only where at least three raters give a strict majority."""
    result: list[AnnotationFinding] = []
    for group in sample_groups(batch):
        rated = [item for item in group if item.labels is not None]
        if len(rated) < 3:  # noqa: PLR2004  # A minority requires at least three raters.
            continue
        counts = Counter(tuple(sorted(set(item.labels or ()))) for item in rated)
        majority, count = counts.most_common(1)[0]
        if count * 2 <= len(rated):
            continue
        for item in rated:
            actual = tuple(sorted(set(item.labels or ())))
            if actual != majority:
                result.append(
                    finding(
                        item,
                        "minority_label",
                        "Label set differs from a strict annotator majority; review is required",
                        (f"majority={majority}; votes={count}/{len(rated)}", f"observed={actual}"),
                    )
                )
    return tuple(result)


def _majority(group: tuple[AnnotationRecord, ...]) -> tuple[tuple[str, ...], int, int] | None:
    rated = [tuple(sorted(set(item.labels))) for item in group if item.labels is not None]
    if not rated:
        return None
    labels, votes = Counter(rated).most_common(1)[0]
    return (labels, votes, len(rated)) if votes * 2 > len(rated) else None


def duplicate_findings(batch: AnnotationBatch) -> tuple[AnnotationFinding, ...]:
    """Flag supplied near-duplicate pairs whose strict-majority label sets differ."""
    groups = {group[0].sample_id: group for group in sample_groups(batch)}
    result: dict[str, AnnotationFinding] = {}
    for pair in batch.near_duplicates:
        left = groups.get(pair.sample_id, ())
        right = groups.get(pair.other_sample_id, ())
        left_majority, right_majority = _majority(left), _majority(right)
        if (
            pair.sample_id == pair.other_sample_id
            or left_majority is None
            or right_majority is None
            or left_majority[0] == right_majority[0]
        ):
            continue
        evidence = (
            f"pair={pair.sample_id},{pair.other_sample_id}; similarity={pair.similarity}",
            f"{pair.sample_id}: {left_majority[0]} votes={left_majority[1]}/{left_majority[2]}",
            (
                f"{pair.other_sample_id}: {right_majority[0]} "
                f"votes={right_majority[1]}/{right_majority[2]}"
            ),
        )
        for items, majority, other in (
            (left, left_majority[0], pair.other_sample_id),
            (right, right_majority[0], pair.sample_id),
        ):
            for item in items:
                if item.labels is None or tuple(sorted(set(item.labels))) != majority:
                    continue
                candidate = finding(
                    item,
                    "near_duplicate_conflict",
                    "Near-duplicate samples received different majority labels",
                    evidence,
                    key=other,
                    related=(other,),
                )
                result[candidate.finding_id] = candidate
    return tuple(result.values())


def _self_duplicates(item: AnnotationRecord) -> list[AnnotationFinding]:
    result: list[AnnotationFinding] = []
    boxes = item.boxes or ()
    for (i, left), (j, right) in combinations(enumerate(boxes), 2):
        overlap = box_iou(left, right)
        if overlap >= _DUPLICATE_IOU:
            result.append(
                finding(
                    item,
                    "duplicate_bbox",
                    "The same annotator drew two nearly identical boxes",
                    (f"box[{i}] {left.category} vs box[{j}] {right.category}; IoU={overlap:.3f}",),
                    key=f"{i}:{j}",
                )
            )
    spans = item.spans or ()
    for (i, left), (j, right) in combinations(enumerate(spans), 2):
        if (left.start, left.end) == (right.start, right.end):
            result.append(
                finding(
                    item,
                    "duplicate_span",
                    "The same annotator marked identical span offsets twice",
                    (
                        (
                            f"span[{i}] {left.category} vs span[{j}] {right.category}; "
                            f"offsets={left.start}:{left.end}"
                        ),
                    ),
                    key=f"{i}:{j}",
                )
            )
    return result


def box_is_valid(record: AnnotationRecord, box: AnnotationBox) -> bool:
    """Accept positive-size boxes with a nonnegative origin inside declared image bounds."""
    if box.x1 < 0 or box.y1 < 0 or box.x2 <= box.x1 or box.y2 <= box.y1:
        return False
    return not (
        (record.image_width is not None and box.x2 > record.image_width)
        or (record.image_height is not None and box.y2 > record.image_height)
    )


def span_is_valid(record: AnnotationRecord, span: AnnotationSpan) -> bool:
    """Accept nonempty half-open spans inside the declared text length."""
    if span.start < 0 or span.end <= span.start:
        return False
    return record.text_length is None or span.end <= record.text_length


def _bbox_findings(item: AnnotationRecord) -> list[AnnotationFinding]:
    return [
        finding(
            item,
            "invalid_bbox",
            "Box has nonpositive dimensions, negative origin or exceeds image bounds",
            (
                f"box[{index}]={box.x1},{box.y1},{box.x2},{box.y2}",
                f"image={item.image_width}x{item.image_height}",
            ),
            key=str(index),
        )
        for index, box in enumerate(item.boxes or ())
        if not box_is_valid(item, box)
    ]


def _span_findings(item: AnnotationRecord) -> list[AnnotationFinding]:
    return [
        finding(
            item,
            "invalid_span",
            "Span is empty, reversed, negative or exceeds the declared text length",
            (f"span[{index}]={span.start}:{span.end}; text_length={item.text_length}",),
            key=str(index),
        )
        for index, span in enumerate(item.spans or ())
        if not span_is_valid(item, span)
    ]


def structural_findings(batch: AnnotationBatch) -> tuple[AnnotationFinding, ...]:
    """Check box/span bounds and duplicated items within one annotator's record."""
    result: list[AnnotationFinding] = []
    for item in batch.annotations:
        result.extend(_bbox_findings(item))
        result.extend(_span_findings(item))
        result.extend(_self_duplicates(item))
    return tuple(result)
